import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.data.models import Holiday
from src.data.repositories.base import commit_or_conflict
from src.data.repositories.company_repository import CompanyRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.holiday import HolidayCreate

DUPLICATE = "A holiday already exists on this date."


class HolidayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.holidays = HolidayRepository(session)
        self.companies = CompanyRepository(session)

    async def list(
        self, *, company_id: uuid.UUID | None, year: int | None, is_active: bool | None = None
    ) -> Sequence[Holiday]:
        return await self.holidays.list(company_id=company_id, year=year, is_active=is_active)

    async def create(self, data: HolidayCreate) -> Holiday:
        holiday = await self.add_new(data)
        await commit_or_conflict(self.session, DUPLICATE)
        await self.session.refresh(holiday)
        return holiday

    async def add_new(self, data: HolidayCreate) -> Holiday:
        """Every rule of create(), without the commit (used by the bulk import)."""
        if data.company_id is not None and await self.companies.get(data.company_id) is None:
            raise ValidationFailedError("Company not found.")
        if await self.holidays.exists(data.company_id, data.holiday_date):
            raise ConflictError(DUPLICATE)
        return await self.holidays.add(
            Holiday(
                company_id=data.company_id,
                holiday_date=data.holiday_date,
                name=data.name.strip(),
            )
        )

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
