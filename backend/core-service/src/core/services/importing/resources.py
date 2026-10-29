"""The three core-service import resources: how each row becomes a service call.

Natural keys (what makes a row "the same record"), from the database constraints:
  - employees: company + employee code   (uq_employees_company_code: codes are unique
               per company, so the file names the company in a `company` column)
  - companies: name, ignoring case       (uq_companies_name_lower)
  - holidays:  date + company            (uq_holidays_company_date; a blank company is
               the holiday for all companies)

Cells are text. A blank optional cell means "not given": on update it leaves the
current value unchanged. Lists (aliases) are separated by ";"."""

import uuid
from collections.abc import Hashable
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.company_service import CompanyService
from src.core.services.employee_service import EmployeeService
from src.core.services.holiday_service import HolidayService
from src.core.services.importing.runner import Column, Resource, RowError
from src.data.repositories.company_repository import CompanyRepository
from src.data.repositories.employee_repository import EmployeeRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.company import CompanyCreate, CompanyUpdate
from src.schemas.employee import EmployeeCreate, EmployeeUpdate
from src.schemas.holiday import HolidayCreate
from src.schemas.importing import CellError

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _given(row: dict[str, str], *names: str) -> dict[str, str]:
    """Only the non-blank cells: a blank cell is "not given"."""
    return {n: row[n] for n in names if row.get(n, "").strip()}


def _aliases(text: str) -> list[str]:
    return [a.strip() for a in text.split(";") if a.strip()]


async def _company_id(companies: CompanyRepository, name: str) -> uuid.UUID:
    company = await companies.get_by_name(name.strip())
    if company is None:
        raise RowError(
            [CellError(column="company", message=f"No company named '{name}'.")]
        )
    return company.id


def _week_start(text: str) -> int | str:
    value = text.strip().lower()
    if value in WEEKDAYS:
        return WEEKDAYS.index(value)
    if value[:3] in [d[:3] for d in WEEKDAYS] and len(value) == 3:
        return [d[:3] for d in WEEKDAYS].index(value)
    return text  # let the schema say what is wrong with it


# --- employees ------------------------------------------------------------------------

EMPLOYEE_COLUMNS = (
    Column(
        "company", True, "ABC Staffing Solutions Pvt Ltd", "Company name, as in the app"
    ),
    Column("employee_code", True, "SYN-EMP-021", "Unique within the company"),
    Column("full_name", True, "Anita Desai"),
    Column("email", False, "anita.desai@example.com"),
    Column(
        "aliases", False, "Anu; A. Desai", "Other names on timesheets, separated by ;"
    ),
    Column("assignment_start", False, "2026-09-01", "YYYY-MM-DD"),
    Column("assignment_end", False, "", "YYYY-MM-DD, blank = ongoing"),
)


def employees(session: AsyncSession) -> Resource:
    service = EmployeeService(session)
    companies = CompanyRepository(session)
    repo = EmployeeRepository(session)
    fields = ("full_name", "email", "assignment_start", "assignment_end")

    async def parse(row: dict[str, str]) -> tuple[Any, Hashable]:
        given = _given(row, "employee_code", *fields)
        if not row.get("company", "").strip():
            raise RowError([CellError(column="company", message="Field required")])
        company_id = await _company_id(companies, row["company"])
        data = EmployeeCreate(
            company_id=company_id,
            aliases=_aliases(row.get("aliases", "")),
            **given,
        )
        return data, (company_id, data.employee_code.lower())

    async def find(key: Hashable) -> Any:
        assert isinstance(key, tuple)
        company_id, code = key
        return await repo.get_by_code(company_id, code)

    async def update(existing: Any, data: Any, row: dict[str, str]) -> None:
        changes: dict[str, Any] = dict(_given(row, *fields))
        if row.get("aliases", "").strip():
            changes["aliases"] = data.aliases
        await service.apply_changes(existing, EmployeeUpdate(**changes))

    return Resource(
        name="employees",
        columns=EMPLOYEE_COLUMNS,
        natural_key="employee code in the same company",
        parse=parse,
        find=find,
        create=service.add_new,
        update=update,
        column_alias={"company_id": "company"},
    )


# --- companies ------------------------------------------------------------------------

COMPANY_COLUMNS = (
    Column("name", True, "Lakeside Logistics Pvt Ltd"),
    Column("hourly_rate", True, "450.00", "Pay per regular hour"),
    Column("overtime_rate", True, "675.00"),
    Column("holiday_rate", True, "900.00"),
    Column("double_time_rate", False, ""),
    Column("currency", False, "INR", "3 letters, default INR"),
    Column("daily_ot_after", False, "8", "Hours per day before overtime, default 8"),
    Column(
        "weekly_ot_after", False, "40", "Hours per week before overtime, default 40"
    ),
    Column("double_time_after", False, "", "Hours per day before double time"),
    Column("week_start", False, "Monday", "Monday ... Sunday (or 0-6), default Monday"),
    Column(
        "aliases", False, "Lakeside; LLP", "Other names on timesheets, separated by ;"
    ),
)
COMPANY_FIELDS = tuple(
    c.name for c in COMPANY_COLUMNS if c.name not in ("name", "aliases")
)


def companies(session: AsyncSession) -> Resource:
    service = CompanyService(session)
    repo = CompanyRepository(session)

    def values(row: dict[str, str]) -> dict[str, Any]:
        given: dict[str, Any] = dict(_given(row, *COMPANY_FIELDS))
        if "week_start" in given:
            given["week_start"] = _week_start(given["week_start"])
        if "currency" in given:
            given["currency"] = given["currency"].upper()
        return given

    async def parse(row: dict[str, str]) -> tuple[Any, Hashable]:
        data = CompanyCreate(
            name=row.get("name", ""),
            aliases=_aliases(row.get("aliases", "")),
            **values(row),
        )
        return data, data.name.lower()

    async def find(key: Hashable) -> Any:
        return await repo.get_by_name(str(key))

    async def update(existing: Any, data: Any, row: dict[str, str]) -> None:
        changes = values(row)
        if row.get("aliases", "").strip():
            changes["aliases"] = data.aliases
        await service.apply_changes(existing, CompanyUpdate(**changes))

    return Resource(
        name="companies",
        columns=COMPANY_COLUMNS,
        natural_key="company name",
        parse=parse,
        find=find,
        create=service.add_new,
        update=update,
    )


# --- holidays -------------------------------------------------------------------------

HOLIDAY_COLUMNS = (
    Column("holiday_date", True, "2026-12-25", "YYYY-MM-DD"),
    Column("name", True, "Christmas Day"),
    Column(
        "company",
        True,
        "ABC Staffing",
        "Company name (each holiday belongs to one company)",
    ),
)


def holidays(session: AsyncSession) -> Resource:
    service = HolidayService(session)
    companies_repo = CompanyRepository(session)
    repo = HolidayRepository(session)

    async def parse(row: dict[str, str]) -> tuple[Any, Hashable]:
        company = row.get("company", "").strip()
        if not company:
            raise RowError([CellError(column="company", message="Enter the company.")])
        company_id = await _company_id(companies_repo, company)
        data = HolidayCreate(
            company_id=company_id,
            holiday_date=row.get("holiday_date", ""),
            name=row.get("name", ""),
        )
        return data, (company_id, data.holiday_date)

    async def find(key: Hashable) -> Any:
        assert isinstance(key, tuple)
        company_id, holiday_date = key
        assert isinstance(holiday_date, date)
        return await repo.find(company_id, holiday_date)

    async def update(existing: Any, data: Any, row: dict[str, str]) -> None:
        await service.rename(existing, data.name)

    return Resource(
        name="holidays",
        columns=HOLIDAY_COLUMNS,
        natural_key="date for the same company",
        parse=parse,
        find=find,
        create=service.add_new,
        update=update,
        column_alias={"company_id": "company"},
    )


RESOURCES = {"employees": employees, "companies": companies, "holidays": holidays}
COLUMNS = {
    "employees": EMPLOYEE_COLUMNS,
    "companies": COMPANY_COLUMNS,
    "holidays": HOLIDAY_COLUMNS,
}
