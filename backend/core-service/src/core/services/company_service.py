import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.data.models import Company, WhitelistSender
from src.data.repositories.base import commit_or_conflict
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
        if await self.companies.get_by_name(data.name) is not None:
            raise ConflictError(DUPLICATE_NAME)
        company = await self.companies.add(Company(**data.model_dump()))
        await commit_or_conflict(self.session, DUPLICATE_NAME)
        await self.session.refresh(company)
        return company

    async def update(self, company_id: uuid.UUID, data: CompanyUpdate) -> Company:
        company = await self.get(company_id)
        changes = data.model_dump(exclude_unset=True)

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
        await commit_or_conflict(self.session, DUPLICATE_NAME)
        await self.session.refresh(company)  # reload updated_at (set by the database)
        return company

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
