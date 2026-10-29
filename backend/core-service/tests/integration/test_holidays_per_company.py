"""Holidays belong to one company, on a real database: a company is required, the same
holiday can be added to several companies or copied from one, one company's holiday
never applies to another, and the migration turns old "all companies" holidays into one
holiday per company."""

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text

from src.config.settings import settings
from src.core.rbac import tokens
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Holiday
from src.data.repositories.holiday_repository import HolidayRepository

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)


def admin() -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": "admin",
        "name": "Ada Admin",
        "email": "ada@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


SERVICE = Path(__file__).resolve().parents[2]
TABLES = "core.submissions, core.companies, core.holidays, core.audit_events"


def company(name: str) -> Company:
    return Company(
        name=name,
        hourly_rate=Decimal("450"),
        overtime_rate=Decimal("675"),
        holiday_rate=Decimal("900"),
    )


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    async with SessionLocal() as s:
        await s.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        a, b, c = company("Lakeside"), company("Hillview"), company("Riverside")
        s.add_all([a, b, c])
        await s.commit()
        ids = {"a": str(a.id), "b": str(b.id), "c": str(c.id)}
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=admin()
    ) as client:
        yield {"client": client, **ids}
    await engine.dispose()


async def test_a_holiday_needs_a_company(world: dict[str, Any]) -> None:
    client: httpx.AsyncClient = world["client"]
    r = await client.post(
        "/holidays", json={"holiday_date": "2026-12-25", "name": "Christmas"}
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"].endswith("Choose a company.")
    r = await client.post(
        "/holidays",
        json={"company_id": world["a"], "holiday_date": "2026-12-25", "name": "Xmas"},
    )
    assert r.status_code == 201 and r.json()["company_id"] == world["a"]
    again = await client.post(
        "/holidays",
        json={"company_id": world["a"], "holiday_date": "2026-12-25", "name": "X"},
    )
    assert again.status_code == 409
    assert "already has a holiday on this date" in again.json()["detail"]


async def test_one_companys_holiday_never_applies_to_another(
    world: dict[str, Any],
) -> None:
    client: httpx.AsyncClient = world["client"]
    await client.post(
        "/holidays",
        json={
            "company_id": world["a"],
            "holiday_date": "2026-10-20",
            "name": "Foundation Day",
        },
    )
    async with SessionLocal() as s:
        repo = HolidayRepository(s)
        assert await repo.dates_for(uuid.UUID(world["a"])) == {
            date(2026, 10, 20): "Foundation Day"
        }
        assert await repo.dates_for(uuid.UUID(world["b"])) == {}
        assert await repo.dates_for(None) == {}  # no company: no holidays
    listed = (await client.get("/holidays", params={"company_id": world["b"]})).json()
    assert listed == []
    assert len((await client.get("/holidays")).json()) == 1  # every company's


async def test_bulk_create_adds_to_several_companies_and_skips_existing(
    world: dict[str, Any],
) -> None:
    client: httpx.AsyncClient = world["client"]
    await client.post(
        "/holidays",
        json={"company_id": world["b"], "holiday_date": "2026-12-25", "name": "Noel"},
    )
    r = await client.post(
        "/holidays/bulk/create",
        json={
            "company_ids": [
                world["a"],
                world["b"],
                world["c"],
                world["a"],
            ],  # a twice: once
            "holiday_date": "2026-12-25",
            "name": "Christmas",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 2
    assert [(s["company_id"], s["reason"]) for s in body["skipped"]] == [
        (world["b"], "Already has 'Noel' on this date.")
    ]
    unknown = await client.post(
        "/holidays/bulk/create",
        json={
            "company_ids": [world["a"], "00000000-0000-0000-0000-000000000000"],
            "holiday_date": "2026-12-26",
            "name": "Boxing Day",
        },
    )
    assert unknown.status_code == 422  # all or nothing: nothing was added
    async with SessionLocal() as s:
        boxing = (
            await s.scalars(select(Holiday).where(Holiday.name == "Boxing Day"))
        ).all()
    assert boxing == []


async def test_copy_from_another_company(world: dict[str, Any]) -> None:
    client: httpx.AsyncClient = world["client"]
    for day, name in (("2026-10-20", "Foundation Day"), ("2027-01-01", "New Year")):
        await client.post(
            "/holidays",
            json={"company_id": world["a"], "holiday_date": day, "name": name},
        )
    await client.post(
        "/holidays",
        json={"company_id": world["c"], "holiday_date": "2026-10-20", "name": "Own"},
    )
    r = await client.post(
        "/holidays/copy",
        json={
            "from_company_id": world["a"],
            "to_company_ids": [world["b"], world["c"]],
            "year": 2026,
        },
    )
    assert r.status_code == 201, r.text
    assert (
        r.json()["created"] == 1
    )  # b gets Foundation Day; c keeps its own; 2027 not asked
    assert [s["company_id"] for s in r.json()["skipped"]] == [world["c"]]
    b = (await client.get("/holidays", params={"company_id": world["b"]})).json()
    assert [(h["holiday_date"], h["name"]) for h in b] == [
        ("2026-10-20", "Foundation Day")
    ]
    nothing = await client.post(
        "/holidays/copy",
        json={"from_company_id": world["b"], "to_company_ids": [world["b"]]},
    )
    assert nothing.status_code == 422


# --- the migration
# ------------------------------------------------------------------------


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=SERVICE,
        env=env,
        check=True,
        capture_output=True,
    )


async def test_the_migration_gives_every_company_the_old_global_holidays(
    world: dict[str, Any],
) -> None:
    try:
        alembic("downgrade", "c4d8a2e6f0b3")
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO core.holidays (company_id, holiday_date, name, "
                    "is_active) VALUES (NULL, '2026-12-25', 'Christmas', true), (NULL, "
                    "'2026-11-08', 'Diwali', false), (CAST(:a AS uuid), '2026-12-25', "
                    "'Company Christmas', true)"
                ),
                {"a": world["a"]},
            )
        await engine.dispose()
        alembic("upgrade", "head")
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT c.name, h.holiday_date::text, h.name, h.is_active FROM "
                        "core.holidays h JOIN core.companies c ON c.id = h.company_id "
                        "ORDER BY 1, 2"
                    )
                )
            ).all()
            nullable = await s.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns WHERE "
                    "table_schema = 'core' AND table_name = 'holidays' AND column_name "
                    "= 'company_id'"
                )
            )
        assert [tuple(r) for r in rows] == [
            ("Hillview", "2026-11-08", "Diwali", False),
            ("Hillview", "2026-12-25", "Christmas", True),
            ("Lakeside", "2026-11-08", "Diwali", False),
            (
                "Lakeside",
                "2026-12-25",
                "Company Christmas",
                True,
            ),  # its own one is kept
            ("Riverside", "2026-11-08", "Diwali", False),
            ("Riverside", "2026-12-25", "Christmas", True),
        ]
        assert nullable == "NO"
    finally:
        alembic("upgrade", "head")
