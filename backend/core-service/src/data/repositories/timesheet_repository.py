import uuid
from collections.abc import Sequence

from sqlalchemy import select

from src.data.models import Timesheet
from src.data.repositories.base import BaseRepository


class TimesheetRepository(BaseRepository[Timesheet]):
    model = Timesheet

    async def search(
        self,
        *,
        status: str | None,
        submission_id: uuid.UUID | None,
        company_id: uuid.UUID | None,
        employee_id: uuid.UUID | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[Timesheet], int]:
        query = select(Timesheet)
        if status:
            query = query.where(Timesheet.status == status)
        if submission_id is not None:
            query = query.where(Timesheet.submission_id == submission_id)
        if company_id is not None:
            query = query.where(Timesheet.company_id == company_id)
        if employee_id is not None:
            query = query.where(Timesheet.employee_id == employee_id)
        return await self.paginate(
            query.order_by(Timesheet.created_at.desc(), Timesheet.id), page=page, size=size
        )
