import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.core.services.transactions import commit_or_conflict
from src.data.models import Company, Holiday
from src.data.repositories.company_repository import CompanyRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.holiday import (
    HolidayBulkCreate,
    HolidayBulkResult,
    HolidayCopy,
    HolidayCreate,
    HolidaySkipped,
)

DUPLICATE = "This company already has a holiday on this date."


class HolidayService:
    """Holidays belong to one company. Hours worked on a company's (active) holiday are
    paid at its holiday rate and flagged holiday_worked (a reviewer checks them)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.holidays = HolidayRepository(session)
        self.companies = CompanyRepository(session)

    async def list(
        self,
        *,
        company_id: uuid.UUID | None,
        year: int | None,
        is_active: bool | None = None,
    ) -> Sequence[Holiday]:
        return await self.holidays.list(
            company_id=company_id, year=year, is_active=is_active
        )

    async def create(self, data: HolidayCreate) -> Holiday:
        holiday = await self.add_new(data)
        await commit_or_conflict(self.session, DUPLICATE)
        await self.session.refresh(holiday)
        return holiday

    async def add_new(self, data: HolidayCreate) -> Holiday:
        """Every rule of create(), without the commit (used by the bulk import)."""
        company_id = data.company_id
        if company_id is None:  # the schema refuses it already
            raise ValidationFailedError("Choose a company.")
        if await self.companies.get(company_id) is None:
            raise ValidationFailedError("Company not found.")
        if await self.holidays.exists(company_id, data.holiday_date):
            raise ConflictError(DUPLICATE)
        return await self.holidays.add(
            Holiday(
                company_id=company_id,
                holiday_date=data.holiday_date,
                name=data.name.strip(),
            )
        )

    async def _known(self, company_ids: Sequence[uuid.UUID]) -> tuple[uuid.UUID, ...]:
        """The ids, once each, in order; 422 naming any company that does not exist."""
        wanted = tuple(dict.fromkeys(company_ids))
        found = set(
            (
                await self.session.scalars(
                    select(Company.id).where(Company.id.in_(wanted))
                )
            ).all()
        )
        missing = [str(c) for c in wanted if c not in found]
        if missing:
            raise ValidationFailedError(f"Company not found: {', '.join(missing)}.")
        return wanted

    async def bulk_create(self, data: HolidayBulkCreate) -> HolidayBulkResult:
        """The same holiday for several companies, in one transaction. A company that
        already has a holiday on that date is skipped (and listed)."""
        name = data.name.strip()
        if not name:
            raise ValidationFailedError("Name cannot be blank.")
        company_ids = await self._known(data.company_ids)
        taken = await self.holidays.dates_taken(company_ids, [data.holiday_date])
        skipped: list[HolidaySkipped] = []
        created = 0
        for company_id in company_ids:
            existing = taken.get((company_id, data.holiday_date))
            if existing is not None:
                skipped.append(
                    HolidaySkipped(
                        company_id=company_id,
                        holiday_date=data.holiday_date,
                        reason=f"Already has '{existing}' on this date.",
                    )
                )
                continue
            await self.holidays.add(
                Holiday(
                    company_id=company_id, holiday_date=data.holiday_date, name=name
                )
            )
            created += 1
        await commit_or_conflict(self.session, DUPLICATE)
        return HolidayBulkResult(created=created, skipped=skipped)

    async def copy(self, data: HolidayCopy) -> HolidayBulkResult:
        """Copy a company's holidays (one year, or all) to other companies, active state
        included, in one transaction. Dates a target already has are skipped."""
        if await self.companies.get(data.from_company_id) is None:
            raise ValidationFailedError("The company to copy from was not found.")
        targets = [
            c
            for c in await self._known(data.to_company_ids)
            if c != data.from_company_id
        ]
        if not targets:
            raise ValidationFailedError("Choose at least one other company to copy to.")
        source = await self.holidays.list(
            company_id=data.from_company_id, year=data.year
        )
        if not source:
            raise ValidationFailedError("That company has no holidays to copy.")
        taken = await self.holidays.dates_taken(
            targets, [h.holiday_date for h in source]
        )
        skipped: list[HolidaySkipped] = []
        created = 0
        for company_id in targets:
            for holiday in source:
                existing = taken.get((company_id, holiday.holiday_date))
                if existing is not None:
                    skipped.append(
                        HolidaySkipped(
                            company_id=company_id,
                            holiday_date=holiday.holiday_date,
                            reason=f"Already has '{existing}' on this date.",
                        )
                    )
                    continue
                await self.holidays.add(
                    Holiday(
                        company_id=company_id,
                        holiday_date=holiday.holiday_date,
                        name=holiday.name,
                        is_active=holiday.is_active,
                    )
                )
                created += 1
        await commit_or_conflict(self.session, DUPLICATE)
        return HolidayBulkResult(created=created, skipped=skipped)

    async def rename(self, holiday: Holiday, name: str) -> None:
        """The only thing that changes on an existing holiday (date and company are its
        identity). No commit: used by the bulk import."""
        name = name.strip()
        if not name:
            raise ValidationFailedError("Name cannot be blank.")
        holiday.name = name
        await self.session.flush()

    async def delete(self, holiday_id: uuid.UUID) -> None:
        holiday = await self.holidays.get(holiday_id)
        if holiday is None:
            raise NotFoundError("Holiday not found.")
        await self.holidays.delete(holiday)
        await self.session.commit()
