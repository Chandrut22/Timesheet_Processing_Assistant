"""Rate limiting for every endpoint, counted in Redis.

Each request falls into one route class (strict / upload / default), resolved
from ROUTE_CLASSES below: one table, so a new route lands in "default" automatically.
Each class has its own limit ("requests/window_seconds" in settings) and its own
counters, keyed by the signed-in user (the "sub" of the verified token claims the auth
middleware put on request.state.principal) or, for anonymous calls and the strict class
(sign-in, refresh, password reset and change), by the client IP.

Counting: a fixed window. INCR on auth:rl:<class>:<who>:<window number> and EXPIRE NX
run in one MULTI/EXEC transaction, so the counter and its expiry are set atomically and
no key can be left without a TTL.

Every response gets X-RateLimit-Limit / -Remaining / -Reset (seconds until the window
resets). Over the limit: 429 {"detail", "code": "rate_limited"} with Retry-After.
Redis down: RATE_LIMIT_FAIL_OPEN=true lets the request through (with a warning in the
log, at most once a minute); false answers 503.

Client IP: the socket address, unless TRUSTED_PROXY_HOPS > 0, then the address our own
proxy (nginx) put in X-Forwarded-For, counted from the right; anything further left
was written by the client and is ignored. Pure ASGI, like the auth middleware."""

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


ROUTE_CLASSES: tuple[tuple[str, str], ...] = (
    ("/auth/login", "strict"),
    ("/auth/refresh", "strict"),
    ("/auth/forgot-password", "strict"),
    ("/auth/reset-password", "strict"),
    ("/auth/change-password", "strict"),
    ("/users/import", "upload"),
    ("/users/import/*", "upload"),
)
DEFAULT_CLASS = "default"
IP_ONLY_CLASSES = frozenset({"strict"})  # sign-in endpoints: always per IP
WARN_EVERY_S = 60


@dataclass(frozen=True, slots=True)
class Limit:
    requests: int
    window_s: int

    @classmethod
    def parse(cls, text: str) -> "Limit":
        """'10/60' -> 10 requests per 60 seconds."""
        requests, _, window = text.partition("/")
        limit = cls(int(requests), int(window))
        if limit.requests < 1 or limit.window_s < 1:
            raise ValueError(f"Rate limit must be like '10/60', got {text!r}")
        return limit


def route_class(path: str, table: Iterable[tuple[str, str]] = ROUTE_CLASSES) -> str:
    path = path.rstrip("/") or "/"
    for pattern, name in table:
        if pattern.endswith("/*"):
            if path.startswith(pattern[:-1]):
                return name
        elif path == pattern:
            return name
    return DEFAULT_CLASS


def client_ip(scope: Scope, trusted_hops: int) -> str:
    """The client address: from X-Forwarded-For only as far as our own proxies wrote it."""
    socket_ip = (scope.get("client") or ("unknown", 0))[0]
    if trusted_hops <= 0:
        return str(socket_ip)
    forwarded = Headers(scope=scope).get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if len(hops) < trusted_hops:
        return str(socket_ip)  # fewer entries than proxies we trust: header not ours
    return hops[-trusted_hops]


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        redis: Any,
        prefix: str,
        limits: dict[str, Limit],
        enabled: bool = True,
        fail_open: bool = True,
        trusted_proxy_hops: int = 1,
        exempt_paths: Iterable[str] = (),
        identify: Callable[[Any], str | None] = lambda principal: None,
        table: Iterable[tuple[str, str]] = ROUTE_CLASSES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self.redis = redis
        self.prefix = prefix
        self.limits = limits
        self.enabled = enabled
        self.fail_open = fail_open
        self.hops = trusted_proxy_hops
        self.exempt = frozenset(p.rstrip("/") or "/" for p in exempt_paths)
        self.identify = identify  # request.state.principal -> user id, or None
        self.table = tuple(table)
        self.clock = clock
        self._last_warning = 0.0

    def _who(self, scope: Scope, name: str) -> str:
        if name not in IP_ONLY_CLASSES:
            user = self.identify(scope.get("state", {}).get("principal"))
            if user:
                return f"u:{user}"
        return f"ip:{client_ip(scope, self.hops)}"

    async def _count(self, key: str, window_s: int) -> int:
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_s + 1, nx=True)
            count, _ = await pipe.execute()
        return int(count)

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
        name = route_class(path, self.table)
        limit = self.limits.get(name) or self.limits[DEFAULT_CLASS]
        now = self.clock()
        window = int(now // limit.window_s)
        reset_in = max(1, math.ceil((window + 1) * limit.window_s - now))
        key = f"{self.prefix}:rl:{name}:{self._who(scope, name)}:{window}"
        try:
            count = await self._count(key, limit.window_s)
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

        headers = {
            "X-RateLimit-Limit": str(limit.requests),
            "X-RateLimit-Remaining": str(max(0, limit.requests - count)),
            "X-RateLimit-Reset": str(reset_in),
        }
        if count > limit.requests:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": f"Too many requests. Try again in {reset_in} seconds.",
                    "code": "rate_limited",
                },
                headers={**headers, "Retry-After": str(reset_in)},
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
