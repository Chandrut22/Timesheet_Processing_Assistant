"""Activate / deactivate many employees, companies and holidays at once, and delete
many holidays, through the HTTP API on a real database (see conftest.py)."""

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
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import AuditEvent, Company, Employee, Holiday
from src.data.repositories.holiday_repository import HolidayRepository

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)


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


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    async with SessionLocal() as s:
        await s.execute(
            text("TRUNCATE core.companies, core.holidays, core.audit_events CASCADE")
        )
        await s.commit()
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=bearer()
    ) as c:
        yield c
    await engine.dispose()


async def company(
    name: str, *employees: str, active: bool = True
) -> tuple[Company, list[Employee]]:
    async with SessionLocal() as s:
        row = Company(
            name=name,
            hourly_rate=Decimal("450"),
            overtime_rate=Decimal("675"),
            holiday_rate=Decimal("900"),
            is_active=active,
        )
        s.add(row)
        await s.flush()
        people = [
            Employee(company_id=row.id, employee_code=f"E{i}", full_name=n)
            for i, n in enumerate(employees, start=1)
        ]
        s.add_all(people)
        await s.commit()
        return row, people


TABLES = {Employee: "employees", Company: "companies", Holiday: "holidays"}


async def is_active(
    model: type[Employee | Company | Holiday], ids: list[uuid.UUID]
) -> list[bool]:
    async with SessionLocal() as s:
        rows = await s.execute(
            text(
                f"SELECT id, is_active FROM core.{TABLES[model]} WHERE id = ANY(:ids)"
            ),  # noqa: S608
            {"ids": ids},
        )
        found = {row.id: row.is_active for row in rows}
        return [found[i] for i in ids]


async def actions(entity_id: uuid.UUID) -> list[str]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at)
        )
        return list(rows.all())


def body(ids: list[uuid.UUID], active: bool) -> dict[str, object]:
    return {"ids": [str(i) for i in ids], "is_active": active}


async def test_employees_in_bulk(client: httpx.AsyncClient) -> None:
    _, (grace, hari) = await company("Lakeside", "Grace", "Hari")
    unknown = uuid.uuid4()
    off = (
        await client.post(
            "/employees/bulk/status", json=body([grace.id, hari.id, unknown], False)
        )
    ).json()
    assert (off["requested"], off["succeeded"], off["failed"]) == (3, 2, 1)
    assert off["results"][2]["error"] == "Employee not found."
    assert await is_active(Employee, [grace.id, hari.id]) == [False, False]
    assert await actions(grace.id) == ["deactivated"]

    again = (
        await client.post("/employees/bulk/status", json=body([grace.id], False))
    ).json()
    assert again["results"][0] == {
        "id": str(grace.id),
        "ok": True,
        "changed": False,
        "is_active": False,
        "error": None,
    }

    on = (
        await client.post("/employees/bulk/status", json=body([grace.id], True))
    ).json()
    assert on["succeeded"] == 1 and await is_active(Employee, [grace.id]) == [True]


async def test_an_employee_of_an_inactive_company_cannot_be_activated(
    client: httpx.AsyncClient,
) -> None:
    _, (priya,) = await company("Closed Co", "Priya", active=False)
    _, (ravi,) = await company("Open Co", "Ravi")
    async with SessionLocal() as s:
        await s.execute(text("UPDATE core.employees SET is_active = false"))
        await s.commit()
    result = (
        await client.post(
            "/employees/bulk/status", json=body([priya.id, ravi.id], True)
        )
    ).json()
    assert [r["ok"] for r in result["results"]] == [False, True]
    assert "Activate the company first" in result["results"][0]["error"]


async def test_deactivating_companies_deactivates_their_employees(
    client: httpx.AsyncClient,
) -> None:
    lakeside, (grace, hari) = await company("Lakeside", "Grace", "Hari")
    northwind, (saran,) = await company("Northwind", "Saran")
    off = (
        await client.post(
            "/companies/bulk/status", json=body([lakeside.id, northwind.id], False)
        )
    ).json()
    assert off["succeeded"] == 2 and off["employees_deactivated"] == 3
    assert await is_active(Company, [lakeside.id, northwind.id]) == [False, False]
    assert await is_active(Employee, [grace.id, hari.id, saran.id]) == [
        False,
        False,
        False,
    ]
    assert await actions(lakeside.id) == ["deactivated"]
    assert await actions(grace.id) == ["deactivated"]

    # Activating the company again does not switch its employees back on.
    on = (
        await client.post("/companies/bulk/status", json=body([lakeside.id], True))
    ).json()
    assert on["succeeded"] == 1 and on["employees_deactivated"] == 0
    assert await is_active(Employee, [grace.id]) == [False]


async def test_a_single_company_edit_also_deactivates_its_employees(
    client: httpx.AsyncClient,
) -> None:
    lakeside, (grace,) = await company("Lakeside", "Grace")
    response = await client.patch(
        f"/companies/{lakeside.id}", json={"is_active": False}
    )
    assert response.status_code == 200
    assert await is_active(Employee, [grace.id]) == [False]


async def test_holidays_active_inactive_and_bulk_delete(
    client: httpx.AsyncClient,
) -> None:
    lakeside, _ = await company("Lakeside")
    async with SessionLocal() as s:
        diwali = Holiday(
            company_id=lakeside.id, holiday_date=date(2026, 11, 8), name="Diwali"
        )
        local = Holiday(
            company_id=lakeside.id, holiday_date=date(2026, 11, 9), name="Founders"
        )
        extra = Holiday(
            company_id=lakeside.id, holiday_date=date(2026, 12, 25), name="Christmas"
        )
        s.add_all([diwali, local, extra])
        await s.commit()

    listed = (await client.get("/holidays")).json()
    assert all(h["is_active"] for h in listed)

    off = (
        await client.post(
            "/holidays/bulk/status", json=body([diwali.id, local.id], False)
        )
    ).json()
    assert off["succeeded"] == 2
    async with SessionLocal() as s:  # an inactive holiday no longer counts in pay
        assert await HolidayRepository(s).dates_for(lakeside.id) == {
            date(2026, 12, 25): "Christmas"
        }
    inactive = (await client.get("/holidays", params={"is_active": "false"})).json()
    assert {h["name"] for h in inactive} == {"Diwali", "Founders"}

    gone = (
        await client.post(
            "/holidays/bulk/delete", json={"ids": [str(extra.id), str(uuid.uuid4())]}
        )
    ).json()
    assert (gone["requested"], gone["deleted"], gone["failed"]) == (2, 1, 1)
    assert {h["name"] for h in (await client.get("/holidays")).json()} == {
        "Diwali",
        "Founders",
    }
    assert await actions(extra.id) == ["deleted"]


async def test_admins_only_and_valid_requests(client: httpx.AsyncClient) -> None:
    _, (grace,) = await company("Lakeside", "Grace")
    request = body([grace.id], False)
    for path in (
        "/employees/bulk/status",
        "/companies/bulk/status",
        "/holidays/bulk/status",
    ):
        assert (
            await client.post(path, json=request, headers=bearer("reviewer"))
        ).status_code == 403
        assert (
            await client.post(path, json=request, headers={"Authorization": ""})
        ).status_code == 401
    twice = {"ids": [str(grace.id), str(grace.id)], "is_active": False}
    assert (await client.post("/employees/bulk/status", json=twice)).status_code == 422
    too_many = {"ids": [str(uuid.uuid4()) for _ in range(101)], "is_active": False}
    assert (
        await client.post("/employees/bulk/status", json=too_many)
    ).status_code == 422
    assert (
        await client.post("/holidays/bulk/delete", json={"ids": []})
    ).status_code == 422
