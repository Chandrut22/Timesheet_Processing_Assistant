"""Bulk import of employees, companies and holidays through the HTTP API, on a real
database (see conftest.py)."""

import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import openpyxl
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text

from src.api.middleware.rate_limit import route_class
from src.config.settings import settings
from src.core.rbac import tokens
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import AuditEvent, Company, Employee, Holiday

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)
ABC = "ABC Staffing Solutions Pvt Ltd"


def bearer(role: str = "admin") -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": role,
        "name": "Ada Admin",
        "email": "ada@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


def csv_file(*lines: str, name: str = "import.csv") -> dict[str, Any]:
    return {"file": (name, ("\r\n".join(lines) + "\r\n").encode(), "text/csv")}


def xlsx_file(rows: list[list[Any]], name: str = "import.xlsx") -> dict[str, Any]:
    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return {"file": (name, out.getvalue(), "application/octet-stream")}


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    async with SessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE core.submissions, core.companies, core.holidays, "
                "core.export_batches, core.audit_events CASCADE"
            )
        )
        s.add(Company(name=ABC, hourly_rate=450, overtime_rate=675, holiday_rate=900))
        await s.commit()
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=bearer()
    ) as c:
        yield c
    await engine.dispose()


async def count(model: Any) -> int:
    async with SessionLocal() as s:
        return len((await s.scalars(select(model))).all())


EMP_HEADER = "company,employee_code,full_name,email,aliases,assignment_start,assignment_end"


# --- templates ---------------------------------------------------------------------------


@pytest.mark.parametrize("resource", ["employees", "companies", "holidays"])
async def test_template(client: httpx.AsyncClient, resource: str) -> None:
    r = await client.get(f"/{resource}/import/template")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f"{resource}-import-template.csv" in r.headers["content-disposition"]
    header, example = r.text.lstrip("﻿").splitlines()[:2]
    assert header and example


# --- valid files, dry run -------------------------------------------------------------


async def test_employees_dry_run_writes_nothing_then_commit(client: httpx.AsyncClient) -> None:
    body = csv_file(
        EMP_HEADER,
        f"{ABC},E100,Anita Desai,anita@example.com,Anu; A. Desai,2026-09-01,",
        f"{ABC},E101,Ravi Shah,,,,",
    )
    r = await client.post("/employees/import", files=body)
    report = r.json()
    assert r.status_code == 200, r.text
    assert (report["dry_run"], report["committed"], report["created"]) == (True, False, 2)
    assert await count(Employee) == 0  # dry run: nothing written

    r = await client.post("/employees/import?dry_run=false", files=body)
    assert r.json()["committed"] is True and r.json()["created"] == 2
    async with SessionLocal() as s:
        anita = (await s.scalars(select(Employee).where(Employee.employee_code == "E100"))).one()
    assert anita.aliases == ["Anu", "A. Desai"] and str(anita.assignment_start) == "2026-09-01"


async def test_employees_from_xlsx_with_date_and_number_cells(client: httpx.AsyncClient) -> None:
    rows: list[list[Any]] = [
        EMP_HEADER.split(","),
        [ABC, 1001, "Number Code", None, None, datetime(2026, 9, 1), None],
    ]
    r = await client.post("/employees/import?dry_run=false", files=xlsx_file(rows))
    assert r.json()["created"] == 1, r.text
    async with SessionLocal() as s:
        e = (await s.scalars(select(Employee))).one()
    assert e.employee_code == "1001" and str(e.assignment_start) == "2026-09-01"


async def test_companies_and_holidays_import(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/companies/import?dry_run=false",
        files=csv_file(
            "name,hourly_rate,overtime_rate,holiday_rate,week_start,aliases",
            "Lakeside Logistics,500,750,1000,Sunday,Lakeside; LLP",
        ),
    )
    assert r.json()["created"] == 1, r.text
    r = await client.post(
        "/holidays/import?dry_run=false",
        files=csv_file(
            "holiday_date,name,company",
            "2026-12-25,Christmas Day,",
            f"2026-10-20,Company Day,{ABC}",
        ),
    )
    assert r.json()["created"] == 2, r.text
    async with SessionLocal() as s:
        lake = (await s.scalars(select(Company).where(Company.name == "Lakeside Logistics"))).one()
        global_holiday = (
            await s.scalars(select(Holiday).where(Holiday.company_id.is_(None)))
        ).one()
    assert lake.week_start == 6 and lake.aliases == ["Lakeside", "LLP"]
    assert global_holiday.name == "Christmas Day"


# --- errors, abort vs skip --------------------------------------------------------------


MIXED = (
    EMP_HEADER,
    f"{ABC},E200,Good One,,,,",
    f"{ABC},E201,Bad Email,not-an-email,,,",
    f"{ABC},E202,Bad Dates,,,2026-10-10,2026-10-01",
    "No Such Co,E203,Unknown Company,,,,",
)


async def test_abort_writes_nothing_when_any_row_fails(client: httpx.AsyncClient) -> None:
    r = await client.post("/employees/import?dry_run=false&on_error=abort", files=csv_file(*MIXED))
    report = r.json()
    assert (report["committed"], report["created"], report["failed"]) == (False, 1, 3)
    assert await count(Employee) == 0
    failed = {row["row"]: row["errors"] for row in report["rows"] if row["status"] == "failed"}
    assert failed[3][0]["column"] == "email"
    assert "assignment_end cannot be before assignment_start" in failed[4][0]["message"]
    assert failed[5] == [{"column": "company", "message": "No company named 'No Such Co'."}]
    assert [row["row"] for row in report["rows"]][:3] == [3, 4, 5]  # failed rows first


async def test_skip_writes_the_valid_rows(client: httpx.AsyncClient) -> None:
    r = await client.post("/employees/import?dry_run=false&on_error=skip", files=csv_file(*MIXED))
    report = r.json()
    assert (report["committed"], report["created"], report["failed"]) == (True, 1, 3)
    assert await count(Employee) == 1


async def test_duplicate_inside_the_file(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/employees/import?on_error=skip",
        files=csv_file(EMP_HEADER, f"{ABC},E300,First,,,,", f"{ABC},e300,Second,,,,"),
    )
    rows = {row["row"]: row for row in r.json()["rows"]}
    assert rows[3]["status"] == "failed"
    assert "Same employee code in the same company as row 2" in rows[3]["errors"][0]["message"]


# --- duplicates against the database ---------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "status", "name_after"),
    [
        ("error", "failed", "Old Name"),
        ("skip", "skipped", "Old Name"),
        ("update", "updated", "New Name"),
    ],
)
async def test_employee_duplicate_modes(
    client: httpx.AsyncClient, mode: str, status: str, name_after: str
) -> None:
    await client.post(
        "/employees/import?dry_run=false", files=csv_file(EMP_HEADER, f"{ABC},E400,Old Name,,,,")
    )
    r = await client.post(
        f"/employees/import?dry_run=false&on_error=skip&on_duplicate={mode}",
        files=csv_file(EMP_HEADER, f"{ABC},E400,New Name,,,,"),
    )
    assert r.json()["rows"][0]["status"] == status, r.text
    async with SessionLocal() as s:
        e = (await s.scalars(select(Employee))).one()
    assert e.full_name == name_after


async def test_company_and_holiday_update_modes(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/companies/import?dry_run=false&on_duplicate=update",
        files=csv_file("name,hourly_rate,overtime_rate,holiday_rate", f"{ABC.upper()},460,690,920"),
    )
    assert r.json()["updated"] == 1, r.text
    async with SessionLocal() as s:
        abc = (await s.scalars(select(Company))).one()
    assert float(abc.hourly_rate) == 460 and abc.name == ABC  # matched ignoring case

    await client.post(
        "/holidays/import?dry_run=false", files=csv_file("holiday_date,name", "2026-12-25,Xmas")
    )
    r = await client.post(
        "/holidays/import?dry_run=false&on_duplicate=update",
        files=csv_file("holiday_date,name", "2026-12-25,Christmas Day"),
    )
    assert r.json()["updated"] == 1
    async with SessionLocal() as s:
        assert (await s.scalars(select(Holiday))).one().name == "Christmas Day"


# --- the file itself ---------------------------------------------------------------------


async def test_missing_required_header(client: httpx.AsyncClient) -> None:
    r = await client.post("/employees/import", files=csv_file("company,full_name", f"{ABC},X"))
    assert r.status_code == 422 and "employee_code" in r.json()["detail"]


async def test_unknown_columns_are_warnings(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/holidays/import", files=csv_file("Holiday_Date,NAME,notes", "2026-12-25,Xmas,ignored")
    )
    assert r.status_code == 200 and r.json()["created"] == 1  # headers match ignoring case
    assert r.json()["warnings"] == ["Column 'notes' is not used by the holidays import."]


async def test_oversize_file(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_import_mb", 1)
    big = "holiday_date,name\r\n" + "2026-12-25,X\r\n" * 100_000
    r = await client.post("/holidays/import", files={"file": ("big.csv", big.encode(), "text/csv")})
    assert r.status_code == 422 and "larger than 1 MB" in r.json()["detail"]


async def test_too_many_rows(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_import_rows", 3)
    lines = ["holiday_date,name"] + [f"2026-12-{d:02d},Day {d}" for d in range(1, 6)]
    r = await client.post("/holidays/import", files=csv_file(*lines))
    assert r.status_code == 422 and "5 rows; the limit is 3" in r.json()["detail"]


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("employees.pdf", b"%PDF-1.7"),
        ("employees.csv", b"MZ\x90\x00\x03\x00\x00\x00"),  # a renamed .exe
        ("employees.xlsx", b"just text"),
    ],
)
async def test_wrong_file_type(client: httpx.AsyncClient, name: str, data: bytes) -> None:
    r = await client.post(
        "/employees/import", files={"file": (name, data, "application/octet-stream")}
    )
    assert r.status_code == 422


async def test_formula_like_cells_are_stored_as_plain_text(client: httpx.AsyncClient) -> None:
    formula = '=HYPERLINK("http://evil.example","x")'
    rows: list[list[Any]] = [EMP_HEADER.split(","), [ABC, "E500", formula, None, None, None, None]]
    r = await client.post("/employees/import?dry_run=false", files=xlsx_file(rows))
    assert r.json()["created"] == 1, r.text
    async with SessionLocal() as s:
        assert (await s.scalars(select(Employee))).one().full_name == formula


# --- who may import, audit, rate limit ----------------------------------------------------


async def test_reviewers_get_403_and_anonymous_401(client: httpx.AsyncClient) -> None:
    body = csv_file("holiday_date,name", "2026-12-25,Xmas")
    r = await client.post("/holidays/import", files=body, headers=bearer("reviewer"))
    assert r.status_code == 403
    r = await client.post("/holidays/import", files=body, headers={"Authorization": ""})
    assert r.status_code == 401


async def test_a_committed_import_writes_one_audit_event(client: httpx.AsyncClient) -> None:
    await client.post(
        "/holidays/import?dry_run=false", files=csv_file("holiday_date,name", "2026-12-25,Xmas")
    )
    await client.post(
        "/holidays/import", files=csv_file("holiday_date,name", "2026-12-26,Boxing")
    )  # dry
    async with SessionLocal() as s:
        (event,) = (
            await s.scalars(select(AuditEvent).where(AuditEvent.entity_type == "import"))
        ).all()
    assert event.action == "holidays_imported" and event.actor_name == "Ada Admin"
    assert event.details["created"] == 1 and len(event.details["sha256"]) == 64


def test_imports_are_in_the_upload_rate_limit_class() -> None:
    for resource in ("employees", "companies", "holidays"):
        assert route_class(f"/{resource}/import") == "upload"
        assert route_class(f"/{resource}/import/template") == "upload"
