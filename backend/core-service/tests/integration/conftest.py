"""Integration tests need a real, THROW-AWAY PostgreSQL database (they empty tables).

    TEST_DATABASE_URL=\
    postgresql+asyncpg://postgres:PASSWORD@127.0.0.1:5433/timesheet_test \
        uv run pytest tests/integration

The database name must contain "test", and its migrations must have run
(DATABASE_URL=<same url> uv run alembic upgrade head). Without TEST_DATABASE_URL these
tests are skipped. The URL is set as DATABASE_URL before the app is imported.

Tests that use Redis (the email listener's keys: cursor, heartbeat, locks) also need
TEST_REDIS_URL, a Redis database OTHER than 0, so they never touch the real listener's
cursor, e.g. redis://:PASSWORD@127.0.0.1:6380/15 (the password is REDIS_PASSWORD from
backend/.env). It is set as REDIS_URL; without it those tests are skipped."""

import os
from urllib.parse import urlparse

import pytest

URL = os.environ.get("TEST_DATABASE_URL", "")
SAFE = bool(URL) and "test" in (urlparse(URL).path or "").lower()
if SAFE:
    os.environ["DATABASE_URL"] = URL
    os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
REDIS_SAFE = bool(REDIS_URL) and (urlparse(REDIS_URL).path or "/0").strip("/") not in (
    "",
    "0",
)
if SAFE and REDIS_SAFE:
    os.environ["REDIS_URL"] = REDIS_URL
NEEDS_REDIS = (
    ""
    if REDIS_SAFE
    else "set TEST_REDIS_URL to a Redis database other than 0, e.g. "
    "redis://:PASSWORD@127.0.0.1:6380/15 (these tests delete the listener's keys)"
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "redis: needs TEST_REDIS_URL (a throw-away Redis db)"
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if SAFE:
        if NEEDS_REDIS:
            for item in items:
                if item.get_closest_marker("redis") is not None:
                    item.add_marker(pytest.mark.skip(reason=NEEDS_REDIS))
        return
    reason = (
        "set TEST_DATABASE_URL to a throw-away database whose name contains 'test'"
        if not URL
        else "TEST_DATABASE_URL's database name must contain 'test' (these tests empty "
        "tables)"
    )
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.skip(reason=reason))
