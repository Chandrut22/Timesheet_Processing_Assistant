"""Version history and rollback through the HTTP API, on a real database (see
conftest.py): data changes make versions, approve / reject do not, a rollback restores
an earlier version as a new one, and an exported timesheet cannot be rolled back."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text

from src.config.settings import settings
from src.core.rbac import tokens
from src.core.services.pay_rules import recalculate, rules_from_company
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import (
    AuditEvent,
    Company,
    Employee,
    Submission,
    Timesheet,
    TimesheetEntry,
    TimesheetVersion,
)

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)
MON = date(2026, 10, 12)


def bearer(role: str = "reviewer") -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": role,
        "name": "Rita Reviewer",
        "email": "rita@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


async def seed() -> str:
    """One matched, priced timesheet: Mon-Fri, 8 h a day."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE core.submissions, core.companies, core.export_batches, "
                "core.audit_events CASCADE"
            )
        )
        company = Company(
            name="Lakeside Logistics",
            hourly_rate=Decimal("450"),
            overtime_rate=Decimal("675"),
            holiday_rate=Decimal("900"),
        )
        s.add(company)
        await s.flush()
        employee = Employee(company_id=company.id, employee_code="E001", full_name="Grace Hopper")
        submission = Submission(source="upload", company_id=company.id)
        s.add_all([employee, submission])
        await s.flush()
        timesheet = Timesheet(
            submission_id=submission.id,
            company_id=company.id,
            employee_id=employee.id,
            extracted_name="Grace Hopper",
            week_start=MON,
            status="needs_review",
            regular_hours=Decimal("40"),
            overtime_hours=Decimal("0"),
            double_time_hours=Decimal("0"),
            holiday_hours=Decimal("0"),
            confidence=Decimal("0.95"),
            match_method="code",
            flags=[],
            entries=[
                TimesheetEntry(work_date=MON + timedelta(days=i), hours=Decimal("8"))
                for i in range(5)
            ],
        )
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


def days(n: int, hours: float = 8) -> list[dict[str, object]]:
    return [{"work_date": str(MON + timedelta(days=i)), "hours": hours} for i in range(n)]


async def test_data_changes_make_versions_and_a_rollback_restores_one(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed()
    base = f"/timesheets/{ts_id}"

    # v1 -> v2: the reviewer changes the days
    edited = (await client.patch(f"{base}/entries", json={"entries": days(4, 9)})).json()
    assert edited["version"] == 2
    assert [e["hours"] for e in edited["entries"]] == [9.0, 9.0, 9.0, 9.0]
    assert "id" not in edited["entries"][0]  # a day is known by its date

    # Nothing changed: recalculating makes no version; approving makes none either.
    assert (await client.post(f"{base}/recalculate")).json()["version"] == 2
    approved = (await client.post(f"{base}/approve", json={})).json()
    assert (approved["status"], approved["version"]) == ("approved", 2)

    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["current"], v["change"]) for v in listing] == [
        (2, True, None),
        (1, False, "entries_edited"),
    ]
    assert listing[1]["changed_by_name"] == "Rita Reviewer"
    assert (listing[1]["days"], listing[1]["total_hours"]) == (5, 40.0)
    assert (listing[0]["days"], listing[0]["status"]) == (4, "approved")

    v1 = (await client.get(f"{base}/versions/1")).json()
    assert [e["hours"] for e in v1["entries"]] == [8.0] * 5
    assert v1["gross_amount"] == 18000.0

    # Roll back to v1: becomes v3, back to review, the v2 data kept as a version.
    restored = await client.post(f"{base}/versions/1/restore", json={"reason": "typo in edit"})
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert (body["version"], body["status"]) == (3, "needs_review")
    assert [e["hours"] for e in body["entries"]] == [8.0] * 5
    assert body["gross_amount"] == 18000.0
    assert body["reviewed_by_name"] is None

    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["change"]) for v in listing] == [
        (3, None),
        (2, "rolled_back"),
        (1, "entries_edited"),
    ]
    assert listing[1]["reason"] == "typo in edit"
    assert listing[1]["status"] == "approved"  # what v2 was when it was replaced

    async with SessionLocal() as s:
        actions = (
            await s.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.entity_id == uuid.UUID(ts_id))
                .order_by(AuditEvent.created_at)
            )
        ).all()
        assert actions == ["entries_edited", "recalculated", "approved", "rolled_back"]
        assert (
            await s.scalar(
                select(TimesheetVersion.snapshot["status"].astext).where(
                    TimesheetVersion.timesheet_id == uuid.UUID(ts_id),
                    TimesheetVersion.version == 2,
                )
            )
        ) == "approved"


async def test_rollback_rules(client: httpx.AsyncClient) -> None:
    ts_id = await seed()
    base = f"/timesheets/{ts_id}"
    current = await client.post(f"{base}/versions/1/restore", json={})
    assert current.status_code == 409  # version 1 is the current one
    assert (await client.post(f"{base}/versions/7/restore", json={})).status_code == 404
    assert (await client.get(f"{base}/versions/7")).status_code == 404

    await client.patch(f"{base}/entries", json={"entries": days(3)})
    admin = await client.post(f"{base}/versions/1/restore", json={}, headers=bearer("admin"))
    assert admin.status_code == 200 and admin.json()["version"] == 3

    async with SessionLocal() as s:  # exported: payroll data never changes
        await s.execute(
            text(
                "INSERT INTO core.export_batches (company_id, company_name, week_start, "
                "week_end, row_count, filename, csv_content) SELECT company_id, 'Lakeside', "
                "week_start, week_start + 6, 1, 'x.csv', '' FROM core.timesheets WHERE id = :id"
            ),
            {"id": ts_id},
        )
        await s.execute(
            text(
                "UPDATE core.timesheets SET status = 'exported', reviewed_at = now(), "
                "exported_at = now(), export_batch_id = (SELECT id FROM core.export_batches "
                "LIMIT 1) WHERE id = :id"
            ),
            {"id": ts_id},
        )
        await s.commit()
    exported = await client.post(f"{base}/versions/1/restore", json={})
    assert exported.status_code == 409
    assert "exported" in exported.json()["detail"].lower()


async def test_reading_needs_a_token_and_restoring_needs_a_reviewer(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed()
    anonymous = {"Authorization": ""}
    assert (await client.get(f"/timesheets/{ts_id}/versions", headers=anonymous)).status_code == 401
    restore = await client.post(
        f"/timesheets/{ts_id}/versions/1/restore", json={}, headers=bearer("viewer")
    )
    assert restore.status_code in (401, 403)
