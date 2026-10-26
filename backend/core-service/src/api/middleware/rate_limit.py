"""One rate limit for every endpoint of both services, counted per client IP in Redis.

The rule: at most RATE_LIMIT requests (default "100/60": 100 per 60 seconds) from one
client IP address, whatever the endpoint and whoever is signed in. auth-service and
core-service use the SAME counter (the same Redis keys), so calls to /auth/... and to
/api/... from one IP add up to the same limit. Health checks (RATE_LIMIT_EXEMPT_PATHS)
and CORS preflights are never counted.

Counting: a sliding window. Each IP has one counter per window
(rl:ip:<ip>:<window number>); the estimate is this window's count plus the previous
window's count weighted by how much of it is still inside the last 60 seconds. So the
limit holds in ANY 60 seconds, not only per calendar minute (a fixed window lets 100
through at 12:00:59 and another 100 at 12:01:00). INCR, EXPIRE NX and the read of the
previous counter run in one MULTI/EXEC transaction: one round trip, and no key is ever
left without an expiry.

Every response gets X-RateLimit-Limit / -Remaining / -Reset (seconds until a request
would pass again). Over the limit: 429 {"detail", "code": "rate_limited"} with
Retry-After. Redis down: RATE_LIMIT_FAIL_OPEN=true lets the request through (a warning
in the log, at most once a minute); false answers 503.

Client IP: the X-Real-IP header, which nginx sets on every request it passes on
($remote_addr, overwriting anything a browser sent). Only nginx publishes a port in
docker compose, so a request reaching a service has always come through nginx. Without
the header (a service run on its own, a test) the socket address is used. X-Forwarded-For
is never read. Should a load balancer ever sit in front of nginx, set nginx's real-IP
module (set_real_ip_from / real_ip_header) so $remote_addr is the browser again; nothing
changes here. Pure ASGI, like the auth middleware."""

import ipaddress
import logging
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from redis.exceptions import RedisError
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# The same in auth-service and core-service: one counter per IP across both.
KEY_PREFIX = "rl:ip"
WARN_EVERY_S = 60


@dataclass(frozen=True, slots=True)
class Limit:
    requests: int
    window_s: int

    @classmethod
    def parse(cls, text: str) -> "Limit":
        """'100/60' -> 100 requests per 60 seconds."""
        requests, _, window = text.partition("/")
        limit = cls(int(requests), int(window))
        if limit.requests < 1 or limit.window_s < 1:
            raise ValueError(f"Rate limit must be like '100/60', got {text!r}")
        return limit


def client_ip(scope: Scope) -> str:
    """X-Real-IP (set by nginx) when it holds a valid address, else the socket address."""
    real = Headers(scope=scope).get("x-real-ip", "").strip()
    if real:
        try:
            return str(ipaddress.ip_address(real))
        except ValueError:
            pass  # not an address: never used as part of a Redis key
    return str((scope.get("client") or ("unknown", 0))[0])


@dataclass(frozen=True, slots=True)
class Usage:
    estimate: float  # requests in the last window_s seconds (sliding estimate)
    retry_in: int  # seconds until the estimate is back under the limit (>= 1)


def sliding_usage(current: int, previous: int, elapsed: float, limit: Limit) -> Usage:
    """Pure. `elapsed` = seconds into the current window. The previous window counts
    for the part of it still inside the last window_s seconds."""
    w = limit.window_s
    weight = 1 - elapsed / w
    estimate = current + previous * weight
    if estimate <= limit.requests:
        return Usage(estimate, max(1, math.ceil(w - elapsed)))
    if previous and current <= limit.requests:
        # The previous window's share shrinks as time passes.
        wait = (estimate - limit.requests) / previous * w
    else:
        # This window alone is over: wait for it to end and for its share to shrink.
        wait = (w - elapsed) + (1 - limit.requests / current) * w
    return Usage(estimate, max(1, math.ceil(wait)))


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        redis: Any,
        limit: Limit,
        enabled: bool = True,
        fail_open: bool = True,
        exempt_paths: Iterable[str] = (),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self.redis = redis
        self.limit = limit
        self.enabled = enabled
        self.fail_open = fail_open
        self.exempt = frozenset(p.rstrip("/") or "/" for p in exempt_paths)
        self.clock = clock
        self._last_warning = 0.0

    async def _count(self, ip: str, now: float) -> Usage:
        w = self.limit.window_s
        window = int(now // w)
        key = f"{KEY_PREFIX}:{ip}:{window}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 2 * w + 1, nx=True)  # still read as "previous" next window
            pipe.get(f"{KEY_PREFIX}:{ip}:{window - 1}")
            current, _, previous = await pipe.execute()
        return sliding_usage(int(current), int(previous or 0), now - window * w, self.limit)

    def _warn(self, exc: Exception) -> None:
        now = self.clock()
        if now - self._last_warning >= WARN_EVERY_S:
            self._last_warning = now
            logger.warning("Rate limiting skipped: Redis unavailable (%s)", exc)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not self.enabled
            or scope["method"] == "OPTIONS"
            or (path.rstrip("/") or "/") in self.exempt
        ):
            await self.app(scope, receive, send)
            return
        try:
            usage = await self._count(client_ip(scope), self.clock())
        except (RedisError, OSError, TimeoutError) as exc:
            if self.fail_open:
                self._warn(exc)
                await self.app(scope, receive, send)
                return
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable. Please try again shortly.",
                    "code": "rate_limit_unavailable",
                },
                headers={"Retry-After": "5"},
            )
            await response(scope, receive, send)
            return

        limit = self.limit.requests
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - math.ceil(usage.estimate))),
            "X-RateLimit-Reset": str(usage.retry_in),
        }
        if usage.estimate > limit:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": f"Too many requests. Try again in {usage.retry_in} seconds.",
                    "code": "rate_limited",
                },
                headers={**headers, "Retry-After": str(usage.retry_in)},
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for header, value in headers.items():
                    response_headers[header] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
