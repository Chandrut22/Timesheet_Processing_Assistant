"""The request log line and the HTTP metrics: what is recorded, what is skipped."""

import logging
import uuid
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from src.api.middleware.logging import RequestLoggingMiddleware
from src.api.middleware.metrics import MetricsMiddleware, route_of


def app_with(middleware: Any, **kwargs: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        if item_id == "missing":
            raise HTTPException(404)
        return {"id": item_id}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    app.add_middleware(middleware, skip_paths=["/health"], **kwargs)
    return app


def test_one_line_per_request_without_the_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(app_with(RequestLoggingMiddleware))
    with caplog.at_level(logging.INFO, logger="http"):
        client.get("/items/42?email=grace@example.com")
        client.get("/items/missing")
        client.get("/health")
    lines = [r for r in caplog.records if r.name == "http"]
    assert [r.getMessage().rsplit(" ", 2)[0] for r in lines] == [
        "GET /items/42 200",
        "GET /items/missing 404",
    ]
    assert all("grace" not in r.getMessage() for r in lines)
    assert all(r.levelno == logging.INFO for r in lines)


def test_a_server_error_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(
        app_with(RequestLoggingMiddleware), raise_server_exceptions=False
    )
    with caplog.at_level(logging.INFO, logger="http"):
        client.get("/boom")
    (line,) = [r for r in caplog.records if r.name == "http"]
    assert line.levelno == logging.WARNING and " 500 " in line.getMessage()


def test_a_slow_request_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(app_with(RequestLoggingMiddleware, slow_ms=-1))
    with caplog.at_level(logging.INFO, logger="http"):
        client.get("/items/1")
    (line,) = [r for r in caplog.records if r.name == "http"]
    assert line.levelno == logging.WARNING


def test_metrics_count_time_and_label_by_route() -> None:
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")
    client = TestClient(app_with(MetricsMiddleware, meter=meter))
    some_id = str(uuid.uuid4())
    client.get(f"/items/{some_id}")
    client.get(f"/items/{uuid.uuid4()}")
    client.get("/items/missing")
    client.get("/health")  # not measured

    data = reader.get_metrics_data()
    assert data is not None
    points: dict[str, list[Any]] = {}
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                points[metric.name] = list(metric.data.data_points)
    requests = {
        (p.attributes["http.route"], p.attributes["http.response.status_code"]): p.value
        for p in points["http.server.requests"]
    }
    assert requests == {("/items/{id}", 200): 2, ("/items/missing", 404): 1}
    durations = points["http.server.duration"]
    assert sum(p.count for p in durations) == 3
    (active,) = points["http.server.active_requests"]
    assert active.value == 0  # every request finished


@pytest.mark.parametrize(
    ("path", "route"),
    [
        (
            "/api/timesheets/3f2a1c9e-1d4b-4a5e-9f60-1b2c3d4e5f60",
            "/api/timesheets/{id}",
        ),
        (
            "/api/timesheets/3f2a1c9e-1d4b-4a5e-9f60-1b2c3d4e5f60/versions/2",
            "/api/timesheets/{id}/versions/{n}",
        ),
        ("/users", "/users"),
        ("/", "/"),
    ],
)
def test_route_of(path: str, route: str) -> None:
    assert route_of(path) == route
