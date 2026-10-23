"""Rate limiting in auth-service: sign-in endpoints are strict and per IP, the rest per
user; 429 with Retry-After; fail-open / fail-closed; spoofed X-Forwarded-For ignored."""

from typing import Any, Self, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.rate_limit import Limit, RateLimitMiddleware, route_class
from src.main import app as real_app


class Clock:
    now = 1_000_020.0  # the start of a 60 s window

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    def __init__(self, clock: Clock) -> None:
        self.clock, self.down = clock, False
        self.values: dict[str, int] = {}
        self.expires: dict[str, float] = {}

    def pipeline(self, transaction: bool = True) -> "FakeRedis":
        assert transaction
        self.ops: list[tuple[str, str, int]] = []
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    def incr(self, key: str) -> None:
        self.ops.append(("incr", key, 0))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        assert nx
        self.ops.append(("expire", key, seconds))

    async def execute(self) -> list[Any]:
        if self.down:
            raise RedisConnectionError("Connection refused")
        out: list[Any] = []
        for op, key, arg in self.ops:
            if self.expires.get(key, float("inf")) <= self.clock.now:
                self.values.pop(key, None), self.expires.pop(key, None)
            if op == "incr":
                self.values[key] = self.values.get(key, 0) + 1
                out.append(self.values[key])
            else:
                self.expires.setdefault(key, self.clock.now + arg)
                out.append(True)
        return out


def make(fail_open: bool = True) -> tuple[TestClient, FakeRedis, Clock]:
    clock = Clock()
    redis = FakeRedis(clock)
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def anything(request: Request) -> dict[str, str]:
        return {}

    app.add_middleware(
        RateLimitMiddleware,
        redis=redis,
        prefix="auth",
        limits={
            "strict": Limit(10, 60),
            "upload": Limit(20, 60),
            "default": Limit(300, 60),
        },
        fail_open=fail_open,
        trusted_proxy_hops=1,
        exempt_paths=["/health", "/health/db"],
        identify=lambda claims: (
            str(claims.get("sub")) if isinstance(claims, dict) else None
        ),
        clock=clock,
    )

    @app.middleware("http")
    async def fake_auth(request: Request, call_next: Any) -> Any:
        sub = request.headers.get("x-sub")
        if sub:
            request.scope.setdefault("state", {})["principal"] = {"sub": sub}
        return await call_next(request)

    return TestClient(app), redis, clock


def test_login_allows_10_a_minute_per_ip_then_429() -> None:
    client, _, _ = make()
    assert all(client.post("/auth/login").status_code == 200 for _ in range(10))
    r = client.post("/auth/login")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert r.json()["code"] == "rate_limited"
    assert r.json()["detail"] == "Too many requests. Try again in 60 seconds."


@pytest.mark.parametrize(
    "path",
    [
        "/auth/login",
        "/auth/refresh",
        "/auth/forgot-password",
        "/auth/reset-password",
        "/auth/change-password",
    ],
)
def test_the_strict_class(path: str) -> None:
    assert route_class(path) == "strict"


def test_strict_and_default_buckets_are_separate() -> None:
    client, _, _ = make()
    for _ in range(11):
        client.post("/auth/login")
    assert client.get("/auth/me", headers={"x-sub": "u1"}).status_code == 200


def test_users_are_counted_by_user_id_and_import_is_upload() -> None:
    client, redis, _ = make()
    client.get("/users", headers={"x-sub": "u1"})
    client.post("/users/import", headers={"x-sub": "u1"})
    assert sorted(k.rsplit(":", 1)[0] for k in redis.values) == [
        "auth:rl:default:u:u1",
        "auth:rl:upload:u:u1",
    ]


def test_window_reset_and_headers() -> None:
    client, _, clock = make()
    for _ in range(11):
        client.post("/auth/login")
    clock.now += 60
    r = client.post("/auth/login")
    assert r.status_code == 200
    assert (r.headers["x-ratelimit-limit"], r.headers["x-ratelimit-remaining"]) == (
        "10",
        "9",
    )


def test_health_is_exempt() -> None:
    client, redis, _ = make()
    for _ in range(50):
        client.get("/health")
    assert redis.values == {}


def test_fail_open_and_fail_closed() -> None:
    client, redis, _ = make(fail_open=True)
    redis.down = True
    assert client.post("/auth/login").status_code == 200
    client, redis, _ = make(fail_open=False)
    redis.down = True
    assert client.post("/auth/login").status_code == 503


def test_spoofed_forwarded_for_cannot_reset_the_login_limit() -> None:
    client, _, _ = make()
    for i in range(10):
        client.post(
            "/auth/login", headers={"x-forwarded-for": f"10.0.0.{i}, 198.51.100.4"}
        )
    r = client.post(
        "/auth/login", headers={"x-forwarded-for": "10.9.9.9, 198.51.100.4"}
    )
    assert r.status_code == 429


def test_the_real_app_runs_cors_then_auth_then_rate_limit() -> None:
    order: list[Any] = [m.cls for m in real_app.user_middleware]  # outermost first
    assert (
        order.index(CORSMiddleware)
        < order.index(AuthMiddleware)
        < order.index(RateLimitMiddleware)
    )
    rate = next(
        m for m in real_app.user_middleware if cast(Any, m.cls) is RateLimitMiddleware
    )
    kwargs = cast(dict[str, Any], rate.kwargs)
    assert kwargs["prefix"] == "auth"
    assert kwargs["limits"]["strict"] == Limit(10, 60)
