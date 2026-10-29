import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import extract, select

from src.data.models import Holiday
from src.data.repositories.base import BaseRepository


class HolidayRepository(BaseRepository[Holiday]):
    """Every holiday belongs to one company."""

    model = Holiday

    async def find(self, company_id: uuid.UUID, holiday_date: date) -> Holiday | None:
        """The company's holiday on this date."""
        found: Holiday | None = await self.session.scalar(
            select(Holiday).where(
                Holiday.company_id == company_id, Holiday.holiday_date == holiday_date
            )
        )
        return found

    async def exists(self, company_id: uuid.UUID, holiday_date: date) -> bool:
        return await self.find(company_id, holiday_date) is not None

    async def list(
        self,
        *,
        company_id: uuid.UUID | None,
        year: int | None,
        is_active: bool | None = None,
    ) -> Sequence[Holiday]:
        """One company's holidays, or (company_id None) every company's."""
        query = select(Holiday)
        if is_active is not None:
            query = query.where(Holiday.is_active.is_(is_active))
        if company_id is not None:
            query = query.where(Holiday.company_id == company_id)
        if year is not None:
            query = query.where(extract("year", Holiday.holiday_date) == year)
        rows = await self.session.scalars(
            query.order_by(Holiday.holiday_date, Holiday.name, Holiday.company_id)
        )
        return rows.all()

    async def dates_for(self, company_id: uuid.UUID | None) -> dict[date, str]:
        """The company's active holidays: date -> name. No company: none (its pay can't
        be worked out anyway). Inactive holidays never count."""
        if company_id is None:
            return {}
        rows = await self.session.execute(
            select(Holiday.holiday_date, Holiday.name).where(
                Holiday.company_id == company_id, Holiday.is_active.is_(True)
            )
        )
        return {row[0]: row[1] for row in rows.all()}

    async def dates_taken(
        self, company_ids: Sequence[uuid.UUID], days: Sequence[date]
    ) -> dict[tuple[uuid.UUID, date], str]:
        """(company, date) -> name of the holidays that already exist, for bulk adds."""
        if not company_ids or not days:
            return {}
        rows = await self.session.execute(
            select(Holiday.company_id, Holiday.holiday_date, Holiday.name).where(
                Holiday.company_id.in_(company_ids), Holiday.holiday_date.in_(days)
            )
        )
        return {(cid, day): name for cid, day, name in rows.all()}
