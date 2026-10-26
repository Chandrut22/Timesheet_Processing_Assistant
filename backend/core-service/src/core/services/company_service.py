import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.core.services.transactions import commit_or_conflict
from src.data.models import Company, Employee, WhitelistSender
from src.data.repositories.company_repository import CompanyRepository, WhitelistRepository
from src.schemas.company import CompanyCreate, CompanyUpdate
from src.utils.senders import normalize_sender

DUPLICATE_NAME = "A company with this name already exists."


def _check_double_time(daily: Decimal, double: Decimal | None, rate: Decimal | None) -> None:
    if double is not None and double <= daily:
        raise ValidationFailedError("double_time_after must be greater than daily_ot_after.")
    if double is not None and rate is None:
        raise ValidationFailedError("double_time_rate is required when double_time_after is set.")


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.companies = CompanyRepository(session)
        self.whitelist = WhitelistRepository(session)

    # --- companies ---------------------------------------------------------

    async def get(self, company_id: uuid.UUID) -> Company:
        company = await self.companies.get(company_id)
        if company is None:
            raise NotFoundError("Company not found.")
        return company

    async def list(
        self, *, q: str | None, is_active: bool | None, page: int, size: int
    ) -> tuple[Sequence[Company], int]:
        return await self.companies.search(q=q, is_active=is_active, page=page, size=size)

    async def create(self, data: CompanyCreate) -> Company:
        company = await self.add_new(data)
        await commit_or_conflict(self.session, DUPLICATE_NAME)
        await self.session.refresh(company)
        return company

    async def add_new(self, data: CompanyCreate) -> Company:
        """Every rule of create(), without the commit (used by the bulk import)."""
        if await self.companies.get_by_name(data.name) is not None:
            raise ConflictError(DUPLICATE_NAME)
        return await self.companies.add(Company(**data.model_dump()))

    async def update(self, company_id: uuid.UUID, data: CompanyUpdate) -> Company:
        company = await self.get(company_id)
        await self.apply_changes(company, data)
        await commit_or_conflict(self.session, DUPLICATE_NAME)
        await self.session.refresh(company)  # reload updated_at (set by the database)
        return company

    async def apply_changes(self, company: Company, data: CompanyUpdate) -> None:
        """Every rule of update(), without the commit (used by the bulk import)."""
        changes = data.model_dump(exclude_unset=True)
        if changes.get("is_active") is False and company.is_active:
            await self.deactivate_employees(company.id)  # an inactive company has none

        new_name = changes.get("name")
        if new_name:
            new_name = new_name.strip()
            existing = await self.companies.get_by_name(new_name)
            if existing is not None and existing.id != company.id:
                raise ConflictError(DUPLICATE_NAME)
            company.name = new_name

        # Required fields: null is ignored. New rates apply to timesheets calculated from
        # now on; every timesheet keeps the rates it was calculated with.
        for field in (
            "aliases",
            "hourly_rate",
            "overtime_rate",
            "holiday_rate",
            "currency",
            "daily_ot_after",
            "weekly_ot_after",
            "week_start",
            "is_active",
        ):
            if changes.get(field) is not None:
                setattr(company, field, changes[field])
        # Optional fields: null is allowed and removes the rule / rate.
        for field in ("double_time_after", "double_time_rate"):
            if field in changes:
                setattr(company, field, changes[field])

        _check_double_time(
            company.daily_ot_after, company.double_time_after, company.double_time_rate
        )
        await self.session.flush()

    async def deactivate_employees(self, company_id: uuid.UUID) -> Sequence[uuid.UUID]:
        """Deactivating a company deactivates its active employees too (activating it
        again does not switch them back on: some may have been inactive before). Returns
        the ids that changed. No commit."""
        rows = await self.session.execute(
            update(Employee)
            .where(Employee.company_id == company_id, Employee.is_active.is_(True))
            .values(is_active=False)
            .returning(Employee.id)
            .execution_options(synchronize_session="fetch")
        )
        return [row[0] for row in rows.all()]

    # --- whitelist ---------------------------------------------------------

    async def list_whitelist(self, company_id: uuid.UUID) -> Sequence[WhitelistSender]:
        await self.get(company_id)
        return await self.whitelist.list_for_company(company_id)

    async def add_whitelist(self, company_id: uuid.UUID, raw_value: str) -> WhitelistSender:
        await self.get(company_id)
        try:
            kind, value = normalize_sender(raw_value)
        except ValueError as exc:
            raise ValidationFailedError(str(exc)) from None

        existing = await self.whitelist.get_by_value(value)
        if existing is not None:
            where = "this company" if existing.company_id == company_id else "another company"
            raise ConflictError(f"'{value}' is already whitelisted for {where}.")

        entry = await self.whitelist.add(
            WhitelistSender(company_id=company_id, kind=kind, value=value)
        )
        await commit_or_conflict(self.session, f"'{value}' is already whitelisted.")
        await self.session.refresh(entry)
        return entry

    async def remove_whitelist(self, company_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        entry = await self.whitelist.get(entry_id)
        if entry is None or entry.company_id != company_id:
            raise NotFoundError("Whitelist entry not found.")
        await self.whitelist.delete(entry)
        await self.session.commit()
