"""Payroll export by a REVIEWER, through the HTTP API, on a real database (see conftest.py):
create, download as CSV and as Excel (the same rows), who created it, and two exports of
the same week at the same moment."""

import asyncio
import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import jwt
import openpyxl
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select, text

from src.config.settings import settings
from src.constants.roles import RoleName
from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import ConflictError
from src.core.rbac import tokens
from src.core.rbac.principal import Principal
from src.core.services.export_service import ExportService
from src.core.services.payroll_csv import CSV_COLUMNS
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Employee, ExportBatch, Submission, Timesheet

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)
WEEK = date(2026, 9, 7)  # a Monday (the company's weeks start on Monday)
REVIEWER_ID = uuid.uuid4()
REVIEWER_NAME = "Rita Reviewer"
NUMERIC = {
    c
    for c in CSV_COLUMNS
    if c.endswith(("_hours", "_rate", "_amount")) or c in ("hourly_rate", "gross_amount")
}


def bearer(role: str, user_id: uuid.UUID, name: str) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "name": name,
        "email": f"{name.split()[0].lower()}@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


async def seed(people: int = 3) -> uuid.UUID:
    """One company and `people` approved, priced timesheets for WEEK. Returns the company id."""
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
        submission = Submission(
            source="upload",
            status="processed",
            received_at=datetime(2026, 9, 14, tzinfo=UTC),
            processed_at=datetime(2026, 9, 14, tzinfo=UTC),
            company_id=company.id,
        )
        s.add(submission)
        await s.flush()
        for n in range(people):
            employee = Employee(
                company_id=company.id, employee_code=f"E{n:03d}", full_name=f"Person {n}"
            )
            s.add(employee)
            await s.flush()
            regular, overtime = Decimal("40"), Decimal(n)
            s.add(
                Timesheet(
                    submission_id=submission.id,
                    company_id=company.id,
                    employee_id=employee.id,
                    extracted_name=employee.full_name,
                    week_start=WEEK,
                    status=TimesheetStatus.APPROVED,
                    reviewed_at=datetime(2026, 9, 14, 10, tzinfo=UTC),
                    reviewed_by_name="Ada Admin",
                    regular_hours=regular,
                    overtime_hours=overtime,
                    currency="INR",
                    hourly_rate=Decimal("450"),
                    overtime_rate=Decimal("675"),
                    holiday_rate=Decimal("900"),
                    regular_amount=regular * 450,
                    overtime_amount=overtime * 675,
                    double_time_amount=Decimal("0"),
                    holiday_amount=Decimal("0"),
                )
            )
        await s.commit()
        return company.id


@pytest.fixture
async def reviewer(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
        headers=bearer("reviewer", REVIEWER_ID, REVIEWER_NAME),
    ) as c:
        yield c
    await engine.dispose()


def csv_rows(body: bytes) -> list[dict[str, str]]:
    assert body.startswith("﻿".encode()), "the CSV starts with a UTF-8 BOM (Excel)"
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def xlsx_rows(body: bytes) -> list[dict[str, Any]]:
    sheet = openpyxl.load_workbook(io.BytesIO(body)).active
    assert sheet is not None
    lines = list(sheet.iter_rows(values_only=True))
    header = [str(h) for h in lines[0]]
    rows = [dict(zip(header, line, strict=True)) for line in lines[1:]]
    return [r for r in rows if r.get("timesheet_id")]  # the last line is the totals row


async def test_reviewer_creates_an_export_and_downloads_both_formats(
    reviewer: httpx.AsyncClient,
) -> None:
    company_id = await seed(people=3)

    preview = await reviewer.get(
        "/exports/preview", params={"company_id": str(company_id), "week_start": WEEK.isoformat()}
    )
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["rows"]) == 3

    created = await reviewer.post(
        "/exports", json={"company_id": str(company_id), "week_start": WEEK.isoformat()}
    )
    assert created.status_code == 201, created.text
    batch = created.json()
    assert batch["row_count"] == 3
    assert batch["created_by_name"] == REVIEWER_NAME

    listed = await reviewer.get("/exports", params={"company_id": str(company_id)})
    assert [b["id"] for b in listed.json()["items"]] == [batch["id"]]

    as_csv = await reviewer.get(f"/exports/{batch['id']}/download")
    assert as_csv.status_code == 200
    assert as_csv.headers["content-type"].startswith("text/csv")
    assert batch["filename"] in as_csv.headers["content-disposition"]
    assert batch["filename"].endswith(".csv")

    as_xlsx = await reviewer.get(f"/exports/{batch['id']}/download", params={"format": "xlsx"})
    assert as_xlsx.status_code == 200
    assert as_xlsx.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert '.xlsx"' in as_xlsx.headers["content-disposition"]

    # The same rows, in the same order, with the same values.
    from_csv, from_xlsx = csv_rows(as_csv.content), xlsx_rows(as_xlsx.content)
    assert len(from_csv) == len(from_xlsx) == 3
    for c, x in zip(from_csv, from_xlsx, strict=True):
        assert x["timesheet_id"] == c["timesheet_id"]
        assert x["employee_code"] == c["employee_code"]
        assert x["employee_name"] == c["employee_name"]
        for column in NUMERIC & c.keys():
            expected = Decimal(c[column]) if c[column] else None
            got = Decimal(str(x[column])) if x[column] is not None else None
            assert got == expected, column


async def test_the_creator_recorded_is_the_reviewer(reviewer: httpx.AsyncClient) -> None:
    company_id = await seed(people=1)
    r = await reviewer.post(
        "/exports", json={"company_id": str(company_id), "week_start": WEEK.isoformat()}
    )
    assert r.status_code == 201, r.text
    async with SessionLocal() as s:
        batch = await s.get(ExportBatch, uuid.UUID(r.json()["id"]))
        assert batch is not None
        assert batch.created_by_id == REVIEWER_ID
        assert batch.created_by_name == REVIEWER_NAME
        exported = (await s.scalars(select(Timesheet))).all()
        assert {t.status for t in exported} == {TimesheetStatus.EXPORTED}
        assert {t.export_batch_id for t in exported} == {batch.id}


async def test_unknown_format_is_refused(reviewer: httpx.AsyncClient) -> None:
    company_id = await seed(people=1)
    r = await reviewer.post(
        "/exports", json={"company_id": str(company_id), "week_start": WEEK.isoformat()}
    )
    bad = await reviewer.get(f"/exports/{r.json()['id']}/download", params={"format": "pdf"})
    assert bad.status_code == 422


async def test_parallel_exports_never_put_a_timesheet_in_two_batches(
    reviewer: httpx.AsyncClient,
) -> None:
    """Two people press "Create" for the same week at the same moment: the row lock
    (SELECT ... FOR UPDATE) makes the second wait, then find nothing left to export."""
    company_id = await seed(people=4)
    people = [
        Principal(
            id=REVIEWER_ID, role=RoleName.REVIEWER, name=REVIEWER_NAME, email="rita@example.com"
        ),
        Principal(id=uuid.uuid4(), role=RoleName.ADMIN, name="Ada Admin", email="ada@example.com"),
    ]

    async def create(actor: Principal) -> uuid.UUID | str:
        async with SessionLocal() as s:
            try:
                batch = await ExportService(s).create(company_id, WEEK, actor)
                await s.commit()
                return batch.id
            except ConflictError as exc:
                await s.rollback()
                return exc.message

    for _ in range(5):  # several rounds: the race is not deterministic
        company_id = await seed(people=4)
        results = await asyncio.gather(*(create(p) for p in people))
        made = [r for r in results if isinstance(r, uuid.UUID)]
        refused = [r for r in results if isinstance(r, str)]
        assert len(made) == 1, results
        assert len(refused) == 1 and "No approved timesheets left" in refused[0]
        async with SessionLocal() as s:
            assert await s.scalar(select(func.count()).select_from(ExportBatch)) == 1
            batch_ids = (await s.scalars(select(Timesheet.export_batch_id))).all()
            assert batch_ids == [made[0]] * 4
