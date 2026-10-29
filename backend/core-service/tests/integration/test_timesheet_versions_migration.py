"""The f4a8c2e6b9d1 migration on a database that already has timesheets: the days move
into timesheets.entries, superseded timesheets become versions of the one that
replaced them, and the downgrade brings timesheet_entries back. Ends at head."""

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

SERVICE = Path(__file__).resolve().parents[2]
BEFORE = "d2f6a4b8c3e5"
SUB = "11111111-1111-1111-1111-111111111111"
RUN = "22222222-2222-2222-2222-222222222222"
V1, V2, V3 = (f"a0000000-0000-0000-0000-00000000000{n}" for n in (1, 2, 3))
ORPHAN = "b0000000-0000-0000-0000-000000000001"

OLD_DATA = f"""
INSERT INTO core.submissions (id, source) VALUES ('{SUB}', 'upload');
INSERT INTO core.reprocess_runs (id, submission_id, reason, requested_by_id,
    requested_by_name, status, before_result, completed_at)
VALUES ('{RUN}', '{SUB}', 'rates fixed', gen_random_uuid(), 'Rita', 'completed',
    '{{}}', now());
INSERT INTO core.timesheets (id, submission_id, extracted_name, version, status,
    regular_hours, reprocess_run_id)
VALUES ('{V3}', '{SUB}', 'Grace', 3, 'needs_review', 40, '{RUN}');
INSERT INTO core.timesheets (id, submission_id, extracted_name, version, status,
    superseded_by_id, regular_hours)
VALUES ('{V2}', '{SUB}', 'Grace', 2, 'superseded', '{V3}', 38),
       ('{ORPHAN}', '{SUB}', 'Hari', 1, 'superseded', NULL, 8);
INSERT INTO core.timesheets (id, submission_id, extracted_name, version, status,
    superseded_by_id, regular_hours)
VALUES ('{V1}', '{SUB}', 'Grace', 1, 'superseded', '{V2}', 36);
INSERT INTO core.timesheet_entries (timesheet_id, work_date, hours, sheet_holiday,
    is_holiday, note)
VALUES ('{V3}', '2026-10-13', 8, false, false, NULL),
       ('{V3}', '2026-10-12', 7.5, true, true, 'Diwali'),
       ('{V1}', '2026-10-12', 6, false, false, NULL);
"""


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=SERVICE,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture
async def db() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    try:
        yield engine
    finally:
        alembic("upgrade", "head")
        async with engine.begin() as conn:
            await conn.execute(text(f"DELETE FROM core.submissions WHERE id = '{SUB}'"))
        await engine.dispose()


async def rows(engine: AsyncEngine, sql: str) -> list[tuple[object, ...]]:
    async with engine.connect() as conn:
        return [tuple(r) for r in (await conn.execute(text(sql))).all()]


async def test_upgrade_moves_days_and_old_versions_and_downgrade_restores(
    db: AsyncEngine,
) -> None:
    alembic("downgrade", BEFORE)
    async with db.begin() as conn:
        await conn.execute(
            text("TRUNCATE core.submissions, core.reprocess_runs CASCADE")
        )
        for statement in OLD_DATA.split(";"):
            if statement.strip():
                await conn.execute(text(statement))

    alembic("upgrade", "head")
    live = await rows(
        db,
        "SELECT extracted_name, version, status, entries, flags FROM core.timesheets "
        "ORDER BY extracted_name",
    )
    assert [(name, version, status) for name, version, status, _, _ in live] == [
        ("Grace", 3, "needs_review"),
        ("Hari", 1, "rejected"),  # superseded with nothing replacing it: kept, flagged
    ]
    grace_days = live[0][3]
    assert grace_days == [
        {
            "work_date": "2026-10-12",
            "hours": 7.5,
            "is_holiday": True,
            "sheet_holiday": True,
            "double_time_marked": False,
            "note": "Diwali",
        },
        {
            "work_date": "2026-10-13",
            "hours": 8,
            "is_holiday": False,
            "sheet_holiday": False,
            "double_time_marked": False,
            "note": None,
        },
    ]
    hari_flags: Any = live[1][4]
    assert [f["code"] for f in hari_flags] == ["removed_by_reprocess"]

    history = await rows(
        db,
        "SELECT timesheet_id::text, version, change, changed_by_name, reason, snapshot "
        "FROM core.timesheet_versions ORDER BY version",
    )
    assert [(h[0], h[1], h[2]) for h in history] == [
        (V3, 1, "reprocessed"),
        (V3, 2, "reprocessed"),
    ]
    assert (history[1][3], history[1][4]) == (
        "Rita",
        "rates fixed",
    )  # the run that replaced v2
    v1 = history[0][5]
    v1 = v1 if isinstance(v1, dict) else json.loads(str(v1))
    assert v1["regular_hours"] == "36.00" and len(v1["entries"]) == 1
    assert v1["status"] == "needs_review"

    alembic("downgrade", BEFORE)
    days = await rows(
        db,
        "SELECT work_date::text, hours, sheet_holiday, note FROM "
        f"core.timesheet_entries WHERE timesheet_id = '{V3}' ORDER BY work_date",
    )
    assert [(d[0], float(d[1]), d[2], d[3]) for d in days] == [  # type: ignore[arg-type]
        ("2026-10-12", 7.5, True, "Diwali"),
        ("2026-10-13", 8.0, False, None),
    ]
