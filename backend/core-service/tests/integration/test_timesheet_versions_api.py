"""Version history and rollback through the HTTP API, on a real database (see
conftest.py): a plain Save edits the current version, "Create as new version" keeps the
old data as a version, approve / reject make none, a restore goes back to a version
(its number too) without making one, and an exported timesheet cannot be restored."""

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
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
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
        employee = Employee(
            company_id=company.id, employee_code="E001", full_name="Grace Hopper"
        )
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
            flags=[
                {
                    "code": "week_assumed",
                    "message": "Week assumed.",
                    "severity": "medium",
                },
                {
                    "code": "handwritten_hours",
                    "message": "By hand.",
                    "severity": "high",
                },
            ],
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
    return [
        {"work_date": str(MON + timedelta(days=i)), "hours": hours} for i in range(n)
    ]


async def test_save_edits_in_place_and_create_as_new_version_keeps_the_old_data(
    client: httpx.AsyncClient,
) -> None:
    ts_id = await seed()
    base = f"/timesheets/{ts_id}"

    # Save: the change goes into version 1; nothing is kept as a version.
    saved = (await client.patch(f"{base}/entries", json={"entries": days(5, 7)})).json()
    assert saved["version"] == 1
    assert [e["hours"] for e in saved["entries"]] == [7.0] * 5
    assert len((await client.get(f"{base}/versions")).json()) == 1

    # "Create as new version": version 1 (as saved above) is kept, the edit is version
    # 2.
    edited = await client.patch(
        f"{base}/entries", json={"entries": days(4, 9), "new_version": True}
    )
    assert edited.status_code == 200, edited.text
    edited_body = edited.json()
    assert edited_body["version"] == 2
    assert [e["hours"] for e in edited_body["entries"]] == [9.0, 9.0, 9.0, 9.0]
    assert "id" not in edited_body["entries"][0]  # a day is known by its date

    # Recalculating and approving save in place: still version 2.
    assert (await client.post(f"{base}/recalculate")).json()["version"] == 2
    approved = (await client.post(f"{base}/approve", json={})).json()
    assert (approved["status"], approved["version"]) == ("approved", 2)

    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["current"], v["change"]) for v in listing] == [
        (2, True, None),
        (1, False, "entries_edited"),
    ]
    assert listing[1]["changed_by_name"] == "Rita Reviewer"
    assert (listing[1]["days"], listing[1]["total_hours"]) == (5, 35.0)
    assert (listing[0]["days"], listing[0]["status"]) == (4, "approved")
    assert "handwritten_hours" in listing[1]["flags"]

    # One version in full: flags come back as codes (they are stored as objects).
    v1 = await client.get(f"{base}/versions/1")
    assert v1.status_code == 200, v1.text
    assert [e["hours"] for e in v1.json()["entries"]] == [7.0] * 5
    assert v1.json()["flags"] == listing[1]["flags"]  # codes, not objects
    gross_v1 = v1.json()["gross_amount"]
    current = await client.get(f"{base}/versions/2")
    assert current.status_code == 200, current.text
    assert current.json()["current"] is True

    # Restore v1: the timesheet IS version 1 again (no new version), back to review,
    # and the v2 data is kept as version 2.
    restored = await client.post(
        f"{base}/versions/1/restore", json={"reason": "typo in edit"}
    )
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert (body["version"], body["status"]) == (1, "needs_review")
    assert [e["hours"] for e in body["entries"]] == [7.0] * 5
    assert body["gross_amount"] == gross_v1
    assert body["reviewed_by_name"] is None

    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["current"], v["change"]) for v in listing] == [
        (2, False, "rolled_back"),
        (1, True, "entries_edited"),
    ]
    assert listing[0]["reason"] == "typo in edit"
    assert listing[0]["status"] == "approved"  # what v2 was when it was left
    assert listing[0]["days"] == 4

    # ... and back to 2: still two versions, nothing lost.
    again = (await client.post(f"{base}/versions/2/restore", json={})).json()
    assert again["version"] == 2
    assert [e["hours"] for e in again["entries"]] == [9.0] * 4
    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["current"]) for v in listing] == [(2, True), (1, False)]

    # Back on 1, a Save edits version 1; "Create as new version" takes the next free
    # number (3), since 2 already exists.
    await client.post(f"{base}/versions/1/restore", json={})
    in_place = (
        await client.patch(f"{base}/entries", json={"entries": days(5, 6)})
    ).json()
    assert in_place["version"] == 1
    newest = (
        await client.patch(
            f"{base}/entries", json={"entries": days(2, 8), "new_version": True}
        )
    ).json()
    assert newest["version"] == 3
    listing = (await client.get(f"{base}/versions")).json()
    assert [(v["version"], v["current"]) for v in listing] == [
        (3, True),
        (2, False),
        (1, False),
    ]
    v1_now = (await client.get(f"{base}/versions/1")).json()
    assert [e["hours"] for e in v1_now["entries"]] == [
        6.0
    ] * 5  # the in-place edit kept

    async with SessionLocal() as s:
        actions = (
            await s.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.entity_id == uuid.UUID(ts_id))
                .order_by(AuditEvent.created_at)
            )
        ).all()
        assert actions == [
            "entries_edited",
            "entries_edited",
            "recalculated",
            "approved",
            "rolled_back",
            "rolled_back",
            "rolled_back",
            "entries_edited",
            "entries_edited",
        ]
        assert (
            await s.scalar(
                select(TimesheetVersion.snapshot["status"].astext).where(
                    TimesheetVersion.timesheet_id == uuid.UUID(ts_id),
                    TimesheetVersion.version == 2,
                )
            )
        ) == "needs_review"  # refreshed when v2 was left the second time


async def test_rollback_rules(client: httpx.AsyncClient) -> None:
    ts_id = await seed()
    base = f"/timesheets/{ts_id}"
    current = await client.post(f"{base}/versions/1/restore", json={})
    assert current.status_code == 409  # version 1 is the current one
    assert (await client.post(f"{base}/versions/7/restore", json={})).status_code == 404
    assert (await client.get(f"{base}/versions/7")).status_code == 404

    await client.patch(
        f"{base}/entries", json={"entries": days(3), "new_version": True}
    )
    admin = await client.post(
        f"{base}/versions/1/restore", json={}, headers=bearer("admin")
    )
    assert admin.status_code == 200 and admin.json()["version"] == 1

    async with SessionLocal() as s:  # exported: payroll data never changes
        await s.execute(
            text(
                "INSERT INTO core.export_batches (company_id, company_name, "
                "week_start, week_end, row_count, filename, csv_content) SELECT "
                "company_id, 'Lakeside', week_start, week_start + 6, 1, 'x.csv', '' "
                "FROM core.timesheets WHERE id = :id"
            ),
            {"id": ts_id},
        )
        await s.execute(
            text(
                "UPDATE core.timesheets SET status = 'exported', reviewed_at = now(), "
                "exported_at = now(), export_batch_id = (SELECT id FROM "
                "core.export_batches LIMIT 1) WHERE id = :id"
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
    assert (
        await client.get(f"/timesheets/{ts_id}/versions", headers=anonymous)
    ).status_code == 401
    restore = await client.post(
        f"/timesheets/{ts_id}/versions/1/restore", json={}, headers=bearer("viewer")
    )
    assert restore.status_code in (401, 403)
