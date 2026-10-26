"""HTTP metrics for every request: how many, how long, how many at once.

OpenTelemetry metrics (observability/metrics/): sent to the collector with the traces and
logs when OTEL_ENABLED and OTEL_EXPORTER_OTLP_ENDPOINT are set; free no-ops otherwise.

  http.server.requests          counter    method, route, status
  http.server.duration          histogram  method, route, status  (milliseconds)
  http.server.active_requests   up-down    method

The route is the path with ids replaced ("/api/timesheets/{id}"), so the number of
series stays small. Health checks are not measured. Pure ASGI."""

import re
import time
from collections.abc import Iterable

from opentelemetry.metrics import Meter
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.observability.metrics.instruments import http_instruments

_UUID = re.compile(r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_NUMBER = re.compile(r"/\d+(?=/|$)")


def route_of(path: str) -> str:
    """'/api/timesheets/3f2a...-.../versions/2' -> '/api/timesheets/{id}/versions/{n}'"""
    return _NUMBER.sub("/{n}", _UUID.sub("/{id}", path)) or "/"


class MetricsMiddleware:
    def __init__(
        self, app: ASGIApp, *, skip_paths: Iterable[str] = (), meter: Meter | None = None
    ) -> None:
        self.app = app
        self.skip = frozenset(p.rstrip("/") or "/" for p in skip_paths)
        self.requests, self.duration, self.active = http_instruments(meter)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or (path.rstrip("/") or "/") in self.skip:
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "-")
        started = time.perf_counter()
        status = 500

        async def send_and_watch(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        self.active.add(1, {"http.request.method": method})
        try:
            await self.app(scope, receive, send_and_watch)
        finally:
            self.active.add(-1, {"http.request.method": method})
            labels = {
                "http.request.method": method,
                "http.route": route_of(path),
                "http.response.status_code": status,
            }
            self.requests.add(1, labels)
            self.duration.record((time.perf_counter() - started) * 1000, labels)
