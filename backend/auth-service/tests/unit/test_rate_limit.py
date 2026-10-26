"""One rate limit for every endpoint: RATE_LIMIT requests per client IP, a sliding
window shared with the other service, 429 with Retry-After, the IP from nginx's
X-Real-IP only, health checks never counted, fail-open / fail-closed."""

import os
import uuid
from typing import Any, Self, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.rate_limit import (
    KEY_PREFIX,
    Limit,
    RateLimitMiddleware,
    client_ip,
    sliding_usage,
)
from src.main import app as real_app

START = 1_000_020.0  # 16667 x 60: the start of a 60 s window


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    """INCR + EXPIRE NX + GET in a MULTI pipeline, with expiry on a fake clock."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.values: dict[str, int] = {}
        self.expires: dict[str, float] = {}
        self.down = False

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        assert transaction, "the counter and its expiry must be set atomically"
        return FakePipeline(self)

    def _expire_old(self, key: str) -> None:
        if key in self.expires and self.expires[key] <= self.clock.now:
            self.values.pop(key, None)
            self.expires.pop(key, None)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple[str, str, int | None]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    def incr(self, key: str) -> None:
        self.ops.append(("incr", key, None))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        assert nx, "EXPIRE NX: never push the expiry further"
        self.ops.append(("expire", key, seconds))

    def get(self, key: str) -> None:
        self.ops.append(("get", key, None))

    async def execute(self) -> list[Any]:
        r = self.redis
        if r.down:
            raise RedisConnectionError("Connection refused")
        out: list[Any] = []
        for op, key, arg in self.ops:
            r._expire_old(key)
            if op == "incr":
                r.values[key] = r.values.get(key, 0) + 1
                out.append(r.values[key])
            elif op == "expire":
                r.expires.setdefault(key, r.clock.now + int(arg or 0))
                out.append(True)
            else:
                value = r.values.get(key)
                out.append(None if value is None else str(value))
        return out


def make(
    *,
    redis: FakeRedis | None = None,
    clock: Clock | None = None,
    fail_open: bool = True,
) -> tuple[TestClient, FakeRedis, Clock]:
    clock = clock or Clock()
    redis = redis or FakeRedis(clock)
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "OPTIONS"])
    async def anything(request: Request) -> dict[str, str]:
        return {"ok": "yes"}

    app.add_middleware(
        RateLimitMiddleware,
        redis=redis,
        limit=Limit(100, 60),
        fail_open=fail_open,
        exempt_paths=["/health"],
        clock=clock,
    )
    return TestClient(app), redis, clock


def ip(address: str) -> dict[str, str]:
    return {"x-real-ip": address}


def test_100_a_minute_then_429_with_retry_after() -> None:
    client, _, _ = make()
    codes = [
        client.get("/timesheets", headers=ip("203.0.113.7")).status_code
        for _ in range(100)
    ]
    assert set(codes) == {200}
    r = client.get("/timesheets", headers=ip("203.0.113.7"))
    assert r.status_code == 429
    assert r.json()["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert r.headers["x-ratelimit-remaining"] == "0"
    assert "Try again in" in r.json()["detail"]


def test_headers_count_down() -> None:
    client, _, _ = make()
    remaining = [
        client.get("/x", headers=ip("203.0.113.7")).headers["x-ratelimit-remaining"]
        for _ in range(3)
    ]
    assert remaining == ["99", "98", "97"]
    assert client.get("/x").headers["x-ratelimit-limit"] == "100"


def test_every_endpoint_shares_the_one_limit() -> None:
    client, _, _ = make()
    paths = ["/auth/login", "/uploads", "/exports", "/timesheets", "/users/import"]
    for n in range(100):
        assert (
            client.post(paths[n % len(paths)], headers=ip("203.0.113.7")).status_code
            == 200
        )
    assert client.post("/auth/login", headers=ip("203.0.113.7")).status_code == 429


def test_the_other_service_counts_in_the_same_counter() -> None:
    """auth-service and core-service share one Redis counter per IP."""
    clock = Clock()
    redis = FakeRedis(clock)
    auth, _, _ = make(redis=redis, clock=clock)
    core, _, _ = make(redis=redis, clock=clock)
    for _ in range(60):
        assert auth.post("/auth/refresh", headers=ip("203.0.113.7")).status_code == 200
    codes = [
        core.get("/api/timesheets", headers=ip("203.0.113.7")).status_code
        for _ in range(41)
    ]
    assert codes[:40] == [200] * 40 and codes[40] == 429
    assert all(k.startswith(f"{KEY_PREFIX}:203.0.113.7:") for k in redis.values)


def test_ips_do_not_affect_each_other() -> None:
    client, _, _ = make()
    for _ in range(101):
        client.get("/x", headers=ip("203.0.113.7"))
    assert client.get("/x", headers=ip("198.51.100.4")).status_code == 200


def test_a_burst_across_the_minute_boundary_is_still_held() -> None:
    client, _, clock = make()
    clock.now = START + 59  # the last second of a window
    assert all(
        client.get("/x", headers=ip("203.0.113.7")).status_code == 200
        for _ in range(100)
    )
    clock.now = START + 61  # one second into the next window: the 100 still count
    codes = [
        client.get("/x", headers=ip("203.0.113.7")).status_code for _ in range(100)
    ]
    # A fixed window would let another 100 through; the sliding estimate (which assumes
    # the earlier minute's requests were spread out) lets through at most one or two.
    assert codes.count(200) <= 2


def test_the_limit_frees_up_as_the_minute_slides() -> None:
    client, _, clock = make()
    for _ in range(100):
        client.get("/x", headers=ip("203.0.113.7"))
    clock.now = (
        START + 60 + 30
    )  # half of the earlier window is still inside the last 60 s
    codes = [client.get("/x", headers=ip("203.0.113.7")).status_code for _ in range(60)]
    assert codes.count(200) == 50 and codes[-1] == 429
    clock.now = START + 60 * 3  # well later: everything has slid out
    assert client.get("/x", headers=ip("203.0.113.7")).status_code == 200


def test_the_ip_comes_from_x_real_ip_and_never_from_x_forwarded_for() -> None:
    client, _, _ = make()
    for n in range(101):  # a new X-Forwarded-For each time cannot reset the counter
        r = client.get(
            "/auth/login",
            headers={"x-real-ip": "203.0.113.7", "x-forwarded-for": f"10.0.0.{n}"},
        )
    assert r.status_code == 429


def test_client_ip_rules() -> None:
    def scope(headers: dict[str, str], socket: str = "172.18.0.5") -> dict[str, Any]:
        raw = [(k.encode(), v.encode()) for k, v in headers.items()]
        return {"type": "http", "headers": raw, "client": (socket, 5000)}

    assert client_ip(scope({"x-real-ip": "203.0.113.7"})) == "203.0.113.7"
    assert client_ip(scope({"x-real-ip": " 2001:db8::1 "})) == "2001:db8::1"
    assert client_ip(scope({})) == "172.18.0.5"  # run without nginx: the socket address
    assert (
        client_ip(scope({"x-real-ip": "not-an-ip:*"})) == "172.18.0.5"
    )  # never in a key
    assert client_ip(scope({"x-forwarded-for": "203.0.113.7"})) == "172.18.0.5"


def test_health_checks_and_preflights_are_not_counted() -> None:
    client, redis, _ = make()
    for _ in range(150):
        assert client.get("/health").status_code == 200
    client.options("/x")
    assert redis.values == {}


def test_fail_open_lets_requests_through_when_redis_is_down() -> None:
    client, redis, _ = make(fail_open=True)
    redis.down = True
    r = client.get("/x")
    assert r.status_code == 200 and "x-ratelimit-limit" not in r.headers


def test_fail_closed_answers_503() -> None:
    client, redis, _ = make(fail_open=False)
    redis.down = True
    r = client.get("/x")
    assert r.status_code == 503 and r.json()["code"] == "rate_limit_unavailable"


def test_sliding_usage_maths() -> None:
    limit = Limit(100, 60)
    assert sliding_usage(10, 0, 0, limit).estimate == 10
    assert sliding_usage(10, 100, 30, limit).estimate == 60  # half the previous window
    over = sliding_usage(101, 0, 10, limit)
    assert over.estimate > 100 and over.retry_in >= 50  # wait for this window to slide
    shrinking = sliding_usage(
        50, 100, 0, limit
    )  # 150: wait until 50 of the 100 slid out
    assert shrinking.retry_in == 30


def test_limit_parsing() -> None:
    assert Limit.parse("100/60") == Limit(100, 60)
    with pytest.raises(ValueError):
        Limit.parse("0/60")


def test_the_real_app_runs_cors_then_auth_then_rate_limit() -> None:
    order: list[Any] = [m.cls for m in real_app.user_middleware]  # outermost first
    assert order.index(CORSMiddleware) < order.index(AuthMiddleware)
    assert order.index(AuthMiddleware) < order.index(RateLimitMiddleware)
    rate = next(
        m for m in real_app.user_middleware if cast(Any, m.cls) is RateLimitMiddleware
    )
    kwargs = cast(dict[str, Any], rate.kwargs)
    assert kwargs["limit"] == Limit(100, 60)  # the default RATE_LIMIT


@pytest.mark.skipif(
    not os.environ.get("RATE_LIMIT_TEST_REDIS_URL"), reason="no test Redis"
)
def test_against_a_real_redis() -> None:
    """RATE_LIMIT_TEST_REDIS_URL=redis://localhost:6379/15 pytest -k real_redis"""
    from redis.asyncio import Redis

    redis = Redis.from_url(
        os.environ["RATE_LIMIT_TEST_REDIS_URL"], decode_responses=True
    )
    app = FastAPI()

    @app.get("/x")
    async def x() -> dict[str, str]:
        return {}

    app.add_middleware(RateLimitMiddleware, redis=redis, limit=Limit(2, 60))
    address = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
    with TestClient(app) as client:  # one event loop for the Redis connection pool
        codes = [client.get("/x", headers=ip(address)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
