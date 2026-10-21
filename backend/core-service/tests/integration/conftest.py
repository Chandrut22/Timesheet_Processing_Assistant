"""Integration tests need a real, THROW-AWAY PostgreSQL database (they empty tables).

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@127.0.0.1:5433/timesheet_test \
        uv run pytest tests/integration

The database name must contain "test", and its migrations must have run
(DATABASE_URL=<same url> uv run alembic upgrade head). Without TEST_DATABASE_URL these
tests are skipped. The URL is set as DATABASE_URL before the app is imported."""

import os
from urllib.parse import urlparse

import pytest

URL = os.environ.get("TEST_DATABASE_URL", "")
SAFE = bool(URL) and "test" in (urlparse(URL).path or "").lower()
if SAFE:
    os.environ["DATABASE_URL"] = URL
    os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if SAFE:
        return
    reason = (
        "set TEST_DATABASE_URL to a throw-away database whose name contains 'test'"
        if not URL
        else "TEST_DATABASE_URL's database name must contain 'test' (these tests empty tables)"
    )
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.skip(reason=reason))
