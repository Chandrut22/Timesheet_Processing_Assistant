import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import extract, or_, select

from src.data.models import Holiday
from src.data.repositories.base import BaseRepository


class HolidayRepository(BaseRepository[Holiday]):
    model = Holiday

    async def exists(self, company_id: uuid.UUID | None, holiday_date: date) -> bool:
        company_filter = (
            Holiday.company_id.is_(None) if company_id is None else Holiday.company_id == company_id
        )
        found = await self.session.scalar(
            select(Holiday.id).where(company_filter, Holiday.holiday_date == holiday_date)
        )
        return found is not None

    async def list(self, *, company_id: uuid.UUID | None, year: int | None) -> Sequence[Holiday]:
        """With company_id: global holidays + that company's. Without: all holidays."""
        query = select(Holiday)
        if company_id is not None:
            query = query.where(or_(Holiday.company_id.is_(None), Holiday.company_id == company_id))
        if year is not None:
            query = query.where(extract("year", Holiday.holiday_date) == year)
        rows = await self.session.scalars(query.order_by(Holiday.holiday_date, Holiday.name))
        return rows.all()
