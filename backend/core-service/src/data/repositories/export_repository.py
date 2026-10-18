import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select

from src.constants.timesheet_status import TimesheetStatus
from src.data.models import Employee, ExportBatch, Timesheet
from src.data.repositories.base import BaseRepository


class ExportRepository(BaseRepository[ExportBatch]):
    model = ExportBatch

    async def search(
        self,
        *,
        company_id: uuid.UUID | None,
        week_start: date | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[ExportBatch], int]:
        query = select(ExportBatch)
        if company_id is not None:
            query = query.where(ExportBatch.company_id == company_id)
        if week_start is not None:
            query = query.where(ExportBatch.week_start == week_start)
        return await self.paginate(
            query.order_by(ExportBatch.created_at.desc(), ExportBatch.id), page=page, size=size
        )

    async def ready_to_export(
        self, company_id: uuid.UUID, week_start: date, *, lock: bool = False
    ) -> list[tuple[Timesheet, Employee]]:
        """Approved, not yet exported timesheets of one company and week, with their employee.

        lock=True takes a row lock (SELECT ... FOR UPDATE OF timesheets): if two admins
        export the same week at once, the second waits, then finds nothing left."""
        query = (
            select(Timesheet, Employee)
            .join(Employee, Employee.id == Timesheet.employee_id)
            .where(
                Timesheet.company_id == company_id,
                Timesheet.week_start == week_start,
                Timesheet.status == TimesheetStatus.APPROVED,
                Timesheet.export_batch_id.is_(None),
            )
            .order_by(Employee.employee_code, Timesheet.id)
        )
        if lock:
            query = query.with_for_update(of=Timesheet)
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def exported_employees(
        self, employee_ids: Sequence[uuid.UUID], week_start: date
    ) -> set[uuid.UUID]:
        """Employees (of the given ones) already in a payroll sheet for this week."""
        if not employee_ids:
            return set()
        rows = await self.session.scalars(
            select(Timesheet.employee_id).where(
                Timesheet.employee_id.in_(employee_ids),
                Timesheet.week_start == week_start,
                Timesheet.status == TimesheetStatus.EXPORTED,
            )
        )
        return {e for e in rows.all() if e is not None}

    async def count_by_status(self, company_id: uuid.UUID, week_start: date) -> dict[str, int]:
        """{"needs_review": 2, "approved": 5, ...} for one company and week."""
        result = await self.session.execute(
            select(Timesheet.status, func.count())
            .where(Timesheet.company_id == company_id, Timesheet.week_start == week_start)
            .group_by(Timesheet.status)
        )
        return {status: count for status, count in result.tuples().all()}
