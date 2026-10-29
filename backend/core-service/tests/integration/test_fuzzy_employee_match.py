"""pg_trgm on a real database: employees.name_keys is kept up to date by Postgres (a
generated column), the shortlist finds close spellings and aliases (per company, or
every company), the employee search finds typos, and matching suggests a close spelling
only after the exact rules."""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.core.services.employee_matcher import apply_match
from src.core.services.pipeline.matching import CompanyContexts, find_employee
from src.core.services.timesheet_validation import blocking_flags, can_auto_approve
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Employee, Timesheet
from src.data.repositories.employee_repository import EmployeeRepository


def company(name: str) -> Company:
    return Company(
        name=name,
        hourly_rate=Decimal("450"),
        overtime_rate=Decimal("675"),
        holiday_rate=Decimal("900"),
    )


@pytest.fixture
async def world() -> AsyncIterator[dict[str, Any]]:
    async with SessionLocal() as s:
        await s.execute(
            text("TRUNCATE core.submissions, core.companies, core.audit_events CASCADE")
        )
        lake, hill = company("Lakeside Logistics"), company("Hillview Staffing")
        s.add_all([lake, hill])
        await s.flush()
        people = {
            "john": Employee(
                company_id=lake.id, employee_code="E7", full_name="John Smith"
            ),
            "rahul": Employee(
                company_id=lake.id, employee_code="E1", full_name="Rahul Kumar"
            ),
            "priya": Employee(
                company_id=lake.id,
                employee_code="E9",
                full_name="Priya Nair",
                aliases=["P. Nair"],
            ),
            "jose": Employee(
                company_id=hill.id, employee_code="H3", full_name="José O'Brien"
            ),
            "gone": Employee(
                company_id=lake.id,
                employee_code="E0",
                full_name="Jon Smyth",
                is_active=False,
            ),
        }
        s.add_all(people.values())
        await s.commit()
        ids = {"lake": lake.id, "hill": hill.id, **{k: e.id for k, e in people.items()}}
    yield ids
    await engine.dispose()


async def name_keys(employee_id: uuid.UUID) -> str | None:
    async with SessionLocal() as s:
        return await s.scalar(
            select(Employee.name_keys).where(Employee.id == employee_id)
        )


async def test_postgres_keeps_name_keys_up_to_date(world: dict[str, Any]) -> None:
    assert await name_keys(world["priya"]) == "priya nair p nair"
    assert (
        await name_keys(world["jose"]) == "jose o brien"
    )  # no accents, no punctuation
    async with SessionLocal() as s:
        priya = await s.get(Employee, world["priya"])
        assert priya is not None
        priya.full_name = "Priya Menon"
        priya.aliases = ["Priya M"]
        await s.commit()
    assert await name_keys(world["priya"]) == "priya menon priya m"


async def test_an_alias_is_found_next_to_the_full_name(world: dict[str, Any]) -> None:
    async with SessionLocal() as s:
        rows = await EmployeeRepository(s).similar_names(
            "P Nair", company_id=world["lake"], min_similarity=0.2
        )
        assert rows[0][0] == world["priya"] and rows[0][2] == 1.0


async def test_the_shortlist_finds_close_spellings(world: dict[str, Any]) -> None:
    async with SessionLocal() as s:
        repo = EmployeeRepository(s)
        rows = await repo.similar_names(
            "Jon Smth", company_id=world["lake"], min_similarity=0.2
        )
        assert [r[0] for r in rows] == [
            world["john"]
        ]  # the inactive Jon Smyth is not listed
        assert 0.3 <= rows[0][2] <= 0.4
        everywhere = await repo.similar_names(
            "Jose OBrien", company_id=None, min_similarity=0.2
        )
        assert everywhere[0][:2] == (world["jose"], world["hill"])
        assert (
            await repo.similar_names("Zed Qwerty", company_id=None, min_similarity=0.2)
            == []
        )


async def test_the_employee_search_finds_typos(world: dict[str, Any]) -> None:
    async with SessionLocal() as s:
        repo = EmployeeRepository(s)
        found, total = await repo.search(
            company_id=world["lake"], q="Jon Smth", is_active=True, page=1, size=20
        )
        assert [e.full_name for e in found] == ["John Smith"] and total == 1
        found, _ = await repo.search(
            company_id=None, q="Rahul", is_active=None, page=1, size=20
        )
        assert found[0].full_name == "Rahul Kumar"  # text in the name comes first
        found, _ = await repo.search(
            company_id=None, q="Jo", is_active=None, page=1, size=20
        )
        # 2 letters: only text in the name (inactive employees too, when asked for all)
        assert {e.full_name for e in found} == {
            "John Smith",
            "José O'Brien",
            "Jon Smyth",
        }


async def test_matching_suggests_a_close_spelling_after_the_exact_rules(
    world: dict[str, Any],
) -> None:
    async with SessionLocal() as s:
        contexts = CompanyContexts(s)
        companies = await contexts.company_records()
        lake = await contexts.get(world["lake"])

        exact = await find_employee(s, lake, "Rahul Kumar", None, companies)
        assert (exact.employee_id, exact.method) == (world["rahul"], "name")

        fuzzy = await find_employee(s, lake, "Jon Smth", None, companies)
        assert (fuzzy.employee_id, fuzzy.method) == (world["john"], "fuzzy")
        t = Timesheet(
            extracted_name="Jon Smth", flags=[], read_confidence=Decimal("0.99")
        )
        apply_match(t, fuzzy, matched=lake.by_id[world["john"]])
        # Never approved on its own: confidence 0.75 (< 0.85) and a blocking flag.
        assert t.confidence == Decimal("0.75")
        assert "fuzzy_match" in {f["code"] for f in blocking_flags(t)}
        assert not can_auto_approve(t)

        nobody = await find_employee(s, lake, "Zed Qwerty", None, companies)
        assert nobody.employee_id is None


async def test_no_company_suggests_names_from_every_company(
    world: dict[str, Any],
) -> None:
    async with SessionLocal() as s:
        contexts = CompanyContexts(s)
        companies = await contexts.company_records()
        unknown = await contexts.get(None)
        result = await find_employee(s, unknown, "Jose O Brian", None, companies)
        assert result.employee_id is None  # never a match without a company
        top = result.candidates[0]
        assert (top.id, top.company_name) == (world["jose"], "Hillview Staffing")


async def test_turned_off(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.config.settings import settings

    monkeypatch.setattr(settings, "match_fuzzy_enabled", False)
    async with SessionLocal() as s:
        contexts = CompanyContexts(s)
        lake = await contexts.get(world["lake"])
        result = await find_employee(
            s, lake, "Jon Smth", None, await contexts.company_records()
        )
        assert result.employee_id is None
