"""Reviewing a weekly-total-only timesheet through the HTTP API, on a real database (see
conftest.py): approve it, move it to another week, turn it into days, export it."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from src.config.settings import settings
from src.core.rbac import tokens
from src.core.services.pay_rules import recalculate, rules_from_company
from src.core.services.timesheet_builder import BuildContext, build_timesheets
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Employee, Submission
from src.schemas.extraction import ExtractedTimesheet

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)
RECEIVED = datetime(2026, 10, 20, 9, tzinfo=UTC)  # Tuesday
ASSUMED_WEEK = date(2026, 10, 12)  # the last full week before it


def bearer() -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": "reviewer",
        "name": "Rita Reviewer",
        "email": "rita@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


async def seed(hours: float) -> str:
    """One totals-only timesheet ("Saran - 42 h"), built and priced like the worker
    does."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE core.submissions, core.companies, core.export_batches, "
                "core.audit_events CASCADE"
            )
        )
        company = Company(
            name="Lakeside Logistics Pvt Ltd",
            hourly_rate=Decimal("450"),
            overtime_rate=Decimal("675"),
            holiday_rate=Decimal("900"),
        )
        s.add(company)
        await s.flush()
        employee = Employee(
            company_id=company.id, employee_code="E001", full_name="Saran"
        )
        submission = Submission(
            source="upload",
            status="processed",
            received_at=RECEIVED,
            processed_at=RECEIVED,
            company_id=company.id,
        )
        s.add_all([employee, submission])
        await s.flush()
        ctx = BuildContext(
            submission_id=submission.id,
            document_id=None,  # type: ignore[arg-type]  # no document needed here
            company_id=company.id,
            received_on=RECEIVED.date(),
            week_start_day=company.week_start,
        )
        [timesheet] = build_timesheets(
            ExtractedTimesheet(
                employee_name="Saran", stated_total=hours, confidence=0.95
            ),
            ctx,
        )
        timesheet.employee_id = employee.id
        recalculate(timesheet, rules_from_company(company), set())
        s.add(timesheet)
        await s.commit()
        return str(timesheet.id)


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=bearer()
    ) as c:
        yield c
    await engine.dispose()


def codes(body: dict[str, object]) -> list[str]:
    return [str(f["code"]) for f in body["flags"]]  # type: ignore[attr-defined]


async def test_the_reviewer_sees_the_total_and_can_approve_and_export_it(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed(42)
    ts = (await client.get(f"/timesheets/{ts_id}")).json()
    assert ts["entries"] == []
    assert (ts["regular_hours"], ts["overtime_hours"], ts["stated_total"]) == (
        40,
        2,
        42,
    )
    assert ts["week_start"] == ASSUMED_WEEK.isoformat()
    assert {"weekly_total_only", "week_assumed"} <= set(codes(ts))
    assert ts["status"] == "needs_review"

    approved = await client.post(f"/timesheets/{ts_id}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    preview = await client.get(
        "/exports/preview",
        params={"company_id": ts["company_id"], "week_start": ASSUMED_WEEK.isoformat()},
    )
    [row] = preview.json()["rows"]
    assert (row["regular_hours"], row["overtime_hours"], row["gross_amount"]) == (
        40,
        2,
        19350,  # 40 x 450 + 2 x 675
    )


async def test_the_reviewer_can_move_it_to_the_right_week(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed(40)
    wednesday = await client.patch(
        f"/timesheets/{ts_id}/week", json={"week_start": "2026-10-07"}
    )
    assert wednesday.status_code == 422
    assert "Monday" in wednesday.json()["detail"]

    moved = await client.patch(
        f"/timesheets/{ts_id}/week", json={"week_start": "2026-10-05"}
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["week_start"] == "2026-10-05"
    assert "week_assumed" not in codes(body)  # the reviewer decided
    assert "weekly_total_only" in codes(body)
    assert body["regular_hours"] == 40


async def test_entering_days_makes_it_a_normal_timesheet(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed(42)
    days = [
        {"work_date": f"2026-10-{d:02d}", "hours": 8, "double_time_marked": False}
        for d in range(12, 17)
    ]
    r = await client.patch(f"/timesheets/{ts_id}/entries", json={"entries": days})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) == 5
    assert "weekly_total_only" not in codes(body)
    assert "week_assumed" not in codes(body)
    assert "total_mismatch" in codes(body)  # the sheet said 42; the days add up to 40
    assert body["regular_hours"] == 40

    # With days, the week follows the days: the week endpoint refuses.
    refused = await client.patch(
        f"/timesheets/{ts_id}/week", json={"week_start": "2026-10-05"}
    )
    assert refused.status_code == 422
