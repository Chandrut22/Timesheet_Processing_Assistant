"""created_at / updated_at / created_by / updated_by: filled from the signed-in user on
every create and change through the API, and NULL (the system) for work done outside a
request. Real database, see conftest.py."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text, update

from src.config.settings import settings
from src.core.rbac import tokens
from src.data.actor import acting_as, current_actor
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Employee

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)
ADA = uuid.uuid4()
RAVI = uuid.uuid4()


def bearer(user_id: uuid.UUID, name: str) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": "admin",
        "name": name,
        "email": f"{name.split()[0].lower()}@example.com",
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
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c
    await engine.dispose()


COMPANY = {
    "name": "Lakeside Logistics",
    "hourly_rate": "450.00",
    "overtime_rate": "675.00",
    "holiday_rate": "900.00",
}


async def test_create_and_change_record_who_and_when(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/companies", json=COMPANY, headers=bearer(ADA, "Ada Admin")
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created_by"] == body["updated_by"] == str(ADA)
    assert body["created_at"] and body["updated_at"]

    changed = await client.patch(
        f"/companies/{body['id']}",
        json={"week_start": 2},
        headers=bearer(RAVI, "Ravi Reviewer"),
    )
    assert changed.status_code == 200, changed.text
    after = changed.json()
    assert after["created_by"] == str(ADA)  # never changes
    assert after["updated_by"] == str(RAVI)
    assert after["created_at"] == body["created_at"]
    assert after["updated_at"] > body["updated_at"]


async def test_holidays_and_senders_have_all_four(client: httpx.AsyncClient) -> None:
    company = (
        await client.post("/companies", json=COMPANY, headers=bearer(ADA, "Ada"))
    ).json()
    holiday = await client.post(
        "/holidays",
        json={
            "company_id": company["id"],
            "holiday_date": "2026-12-25",
            "name": "Christmas",
        },
        headers=bearer(ADA, "Ada Admin"),
    )
    assert holiday.status_code == 201, holiday.text
    h = holiday.json()
    assert h["created_by"] == h["updated_by"] == str(ADA)
    assert h["updated_at"] == h["created_at"]

    sender = await client.post(
        f"/companies/{company['id']}/whitelist",
        json={"value": "lakeside.com"},
        headers=bearer(RAVI, "Ravi Reviewer"),
    )
    assert sender.status_code == 201, sender.text
    assert sender.json()["created_by"] == str(RAVI)


async def test_a_cascade_records_the_admin_on_every_row_it_changes(
    client: httpx.AsyncClient,
) -> None:
    async with SessionLocal() as s:  # made outside a request: the system
        company = Company(
            name="Harbour",
            hourly_rate=Decimal("450"),
            overtime_rate=Decimal("675"),
            holiday_rate=Decimal("900"),
        )
        s.add(company)
        await s.flush()
        s.add(
            Employee(
                company_id=company.id, employee_code="E1", full_name="Grace Hopper"
            )
        )
        await s.commit()
        assert company.created_by is None and company.updated_by is None

    off = await client.post(
        "/companies/bulk/status",
        json={"ids": [str(company.id)], "is_active": False},
        headers=bearer(RAVI, "Ravi Reviewer"),
    )
    assert off.status_code == 200, off.text
    async with SessionLocal() as s:
        employee = (
            await s.execute(select(Employee).where(Employee.company_id == company.id))
        ).scalar_one()
        assert employee.is_active is False
        assert employee.created_by is None
        assert employee.updated_by == RAVI  # an update() statement, not an ORM save


async def test_work_outside_a_request_is_the_system() -> None:
    async with SessionLocal() as s:
        with acting_as(ADA):
            company = Company(
                name="Pier",
                hourly_rate=Decimal("450"),
                overtime_rate=Decimal("675"),
                holiday_rate=Decimal("900"),
            )
            s.add(company)
            await s.commit()
        assert current_actor.get() is None  # acting_as puts it back
        await s.execute(
            update(Company).where(Company.id == company.id).values(week_start=3)
        )
        await s.commit()
        row = (
            await s.execute(
                select(Company.created_by, Company.updated_by).where(
                    Company.id == company.id
                )
            )
        ).one()
        assert row == (ADA, None)  # e.g. a Celery job or the sweeper changed it
    await engine.dispose()
