"""One log line per HTTP request, through OpenTelemetry like every other log record.

    INFO  [http] GET /api/timesheets 200 34 ms

The line has the method, the path (no query string: filters can hold names or emails),
the status and the time taken; written inside the request, so it carries the trace id
when tracing is on. Health checks and long-lived streams (SSE) are not logged. 5xx and
slow requests (over SLOW_MS) are written at WARNING. No headers, no bodies, ever.
Pure ASGI, like the other middleware."""

import logging
import time
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("http")
SLOW_MS = 1000


class RequestLoggingMiddleware:
    def __init__(
        self, app: ASGIApp, *, skip_paths: Iterable[str] = (), slow_ms: int = SLOW_MS
    ) -> None:
        self.app = app
        self.skip = frozenset(p.rstrip("/") or "/" for p in skip_paths)
        self.slow_ms = slow_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or (path.rstrip("/") or "/") in self.skip:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500  # if the app fails before it answers

        async def send_and_watch(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_and_watch)
        finally:
            ms = (time.perf_counter() - started) * 1000
            level = logging.WARNING if status >= 500 or ms > self.slow_ms else logging.INFO
            logger.log(level, "%s %s %d %.0f ms", scope.get("method", "-"), path, status, ms)
