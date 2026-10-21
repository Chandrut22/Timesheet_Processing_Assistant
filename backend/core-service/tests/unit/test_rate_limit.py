"""Rate limiting: per route class, per user or IP, fixed window, 429 with Retry-After,
fail-open / fail-closed, and X-Forwarded-For that cannot be spoofed past our proxy."""

import os
import uuid
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.middleware.rate_limit import (
    Limit,
    RateLimitMiddleware,
    client_ip,
    route_class,
)


class FakeRedis:
    """INCR + EXPIRE NX in a MULTI pipeline, with expiry on a fake clock."""

    def __init__(self, clock: "Clock") -> None:
        self.clock = clock
        self.values: dict[str, int] = {}
        self.expires: dict[str, float] = {}
        self.down = False

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        assert transaction, "the counter and its expiry must be set atomically"
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple[str, str, int | None]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def incr(self, key: str) -> None:
        self.ops.append(("incr", key, None))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        assert nx, "EXPIRE NX: never push the expiry further"
        self.ops.append(("expire", key, seconds))

    async def execute(self) -> list[Any]:
        r = self.redis
        if r.down:
            raise RedisConnectionError("Connection refused")
        out: list[Any] = []
        for op, key, arg in self.ops:
            if key in r.expires and r.expires[key] <= r.clock.now:
                r.values.pop(key, None), r.expires.pop(key, None)
            if op == "incr":
                r.values[key] = r.values.get(key, 0) + 1
                out.append(r.values[key])
            else:
                if key not in r.expires:
                    r.expires[key] = r.clock.now + int(arg or 0)
                out.append(True)
        return out


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_020.0  # 16667 x 60: the start of a 60 s window

    def __call__(self) -> float:
        return self.now


TABLE = (("/auth/login", "strict"), ("/exports/*", "export"))


def make(
    *, fail_open: bool = True, hops: int = 1, limits: dict[str, Limit] | None = None
) -> tuple[TestClient, FakeRedis, Clock]:
    clock = Clock()
    redis = FakeRedis(clock)
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "OPTIONS"])
    async def anything(request: Request) -> dict[str, str]:
        return {"ok": "yes"}

    app.add_middleware(
        RateLimitMiddleware,
        redis=redis,
        prefix="core",
        limits=limits or {"strict": Limit(2, 60), "export": Limit(5, 60), "default": Limit(3, 60)},
        fail_open=fail_open,
        trusted_proxy_hops=hops,
        exempt_paths=["/health"],
        identify=lambda principal: principal,
        table=TABLE,
        clock=clock,
    )

    @app.middleware("http")  # stands in for the auth middleware: X-User -> principal
    async def fake_auth(request: Request, call_next: Any) -> Any:
        user = request.headers.get("x-user")
        if user:
            request.scope.setdefault("state", {})["principal"] = user
        return await call_next(request)

    return TestClient(app), redis, clock


def test_under_the_limit_passes_with_headers() -> None:
    client, _, _ = make()
    remaining = [client.get("/timesheets").headers["x-ratelimit-remaining"] for _ in range(3)]
    assert remaining == ["2", "1", "0"]
    r = client.get("/companies", headers={"x-user": "u2"})
    assert r.headers["x-ratelimit-limit"] == "3" and int(r.headers["x-ratelimit-reset"]) <= 60


def test_over_the_limit_is_429_with_retry_after() -> None:
    client, _, clock = make()
    clock.now += 15  # 45 s left in the window
    for _ in range(3):
        assert client.get("/timesheets").status_code == 200
    r = client.get("/timesheets")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "45"
    assert r.json() == {
        "detail": "Too many requests. Try again in 45 seconds.",
        "code": "rate_limited",
    }
    assert r.headers["x-ratelimit-remaining"] == "0"


def test_strict_and_default_have_separate_buckets() -> None:
    client, _, _ = make()
    for _ in range(2):
        assert client.post("/auth/login").status_code == 200
    assert client.post("/auth/login").status_code == 429  # strict: 2
    assert client.get("/timesheets").status_code == 200  # default bucket untouched


def test_strict_is_per_ip_even_when_signed_in() -> None:
    client, _, _ = make()
    client.post("/auth/login", headers={"x-user": "a"})
    client.post("/auth/login", headers={"x-user": "b"})
    assert client.post("/auth/login", headers={"x-user": "c"}).status_code == 429


def test_signed_in_users_have_their_own_buckets_anonymous_share_the_ip() -> None:
    client, _, _ = make()
    for _ in range(3):
        client.get("/timesheets", headers={"x-user": "alice"})
    assert client.get("/timesheets", headers={"x-user": "alice"}).status_code == 429
    assert client.get("/timesheets", headers={"x-user": "bob"}).status_code == 200
    for _ in range(3):
        client.get("/timesheets")
    assert client.get("/timesheets").status_code == 429  # anonymous: by IP


def test_the_window_resets() -> None:
    client, _, clock = make()
    for _ in range(4):
        client.get("/timesheets")
    clock.now += 61
    assert client.get("/timesheets").status_code == 200


def test_exempt_paths_and_preflights_are_not_counted() -> None:
    client, redis, _ = make()
    for _ in range(10):
        assert client.get("/health").status_code == 200
        assert client.options("/timesheets").status_code == 200
    assert redis.values == {}


def test_export_class_and_keys() -> None:
    client, redis, _ = make()
    client.get("/exports/123/download", headers={"x-user": "alice"})
    (key,) = redis.values
    assert key.startswith("core:rl:export:u:alice:")


def test_fail_open_lets_requests_through_when_redis_is_down() -> None:
    client, redis, _ = make(fail_open=True)
    redis.down = True
    r = client.get("/timesheets")
    assert r.status_code == 200 and "x-ratelimit-limit" not in r.headers


def test_fail_closed_answers_503() -> None:
    client, redis, _ = make(fail_open=False)
    redis.down = True
    r = client.get("/timesheets")
    assert r.status_code == 503 and r.json()["code"] == "rate_limit_unavailable"


def test_spoofed_forwarded_for_is_ignored_beyond_the_trusted_hop() -> None:
    client, redis, _ = make(hops=1)
    for spoof in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        client.get("/timesheets", headers={"x-forwarded-for": f"{spoof}, 203.0.113.9"})
    r = client.get("/timesheets", headers={"x-forwarded-for": "9.9.9.9, 203.0.113.9"})
    assert r.status_code == 429  # every request counted for 203.0.113.9, whatever the client wrote
    assert all(":ip:203.0.113.9:" in k for k in redis.values)


def test_client_ip_rules() -> None:
    def scope(xff: str | None) -> dict[str, Any]:
        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        return {"type": "http", "client": ("172.18.0.5", 5000), "headers": headers}

    assert client_ip(scope("198.51.100.7"), 1) == "198.51.100.7"  # written by nginx
    assert client_ip(scope("evil, 198.51.100.7"), 1) == "198.51.100.7"
    assert client_ip(scope("198.51.100.7"), 0) == "172.18.0.5"  # no proxy trusted
    assert client_ip(scope("only-one"), 2) == "172.18.0.5"  # fewer hops than trusted
    assert client_ip(scope(None), 1) == "172.18.0.5"


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/uploads", "upload"),
        ("/uploads/", "upload"),
        ("/employees/import", "upload"),
        ("/holidays/import/template", "upload"),
        ("/exports", "export"),
        ("/exports/abc/download", "export"),
        ("/exportsx", "default"),
        ("/timesheets", "default"),
        ("/a-route-added-next-year", "default"),
    ],
)
def test_the_route_table(path: str, name: str) -> None:
    assert route_class(path) == name


def test_limit_parsing() -> None:
    assert Limit.parse("10/60") == Limit(10, 60)
    with pytest.raises(ValueError):
        Limit.parse("0/60")


@pytest.mark.skipif(not os.environ.get("RATE_LIMIT_TEST_REDIS_URL"), reason="no test Redis")
def test_against_a_real_redis() -> None:
    """RATE_LIMIT_TEST_REDIS_URL=redis://localhost:6379/15 pytest -k real_redis"""
    from redis.asyncio import Redis

    redis = Redis.from_url(os.environ["RATE_LIMIT_TEST_REDIS_URL"], decode_responses=True)
    app = FastAPI()

    @app.get("/x")
    async def x() -> dict[str, str]:
        return {}

    app.add_middleware(
        RateLimitMiddleware,
        redis=redis,
        prefix=f"test-{uuid.uuid4().hex[:6]}",
        limits={"default": Limit(2, 60)},
    )
    with TestClient(app) as client:  # one event loop for the Redis connection pool
        codes = [client.get("/x").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
