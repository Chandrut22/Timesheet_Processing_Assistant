from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, case, func, or_, select

from src.data.models import Employee, Submission, Timesheet
from src.data.repositories.base import BaseRepository
from src.schemas.timesheet_filters import (
    SeverityFilter,
    SortOrder,
    TimesheetFilters,
    TimesheetSort,
)

SEVERITY_RANK = case(
    (Timesheet.severity == "high", 3),
    (Timesheet.severity == "medium", 2),
    (Timesheet.severity == "low", 1),
    else_=0,
)


def _contains(column: Any, text: str) -> ColumnElement[bool]:
    """Case-insensitive 'contains', with % and _ in the user's text taken literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")  # type: ignore[no-any-return]


def _start_of_day(day: Any) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _conditions(f: TimesheetFilters) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = []

    if f.status:
        where.append(Timesheet.status.in_(f.status))
    if f.state:
        where.append(Submission.state.in_(f.state))
    if f.severity:
        levels = [s.value for s in f.severity if s != SeverityFilter.NONE]
        options: list[ColumnElement[bool]] = []
        if levels:
            options.append(Timesheet.severity.in_(levels))
        if SeverityFilter.NONE in f.severity:
            options.append(Timesheet.severity.is_(None))
        where.append(or_(*options))
    if f.flag:
        where.append(Timesheet.flags.contains([{"code": f.flag}]))

    if f.submission_id is not None:
        where.append(Timesheet.submission_id == f.submission_id)
    if f.company_id is not None:
        where.append(Timesheet.company_id == f.company_id)
    if f.employee_id is not None:
        where.append(Timesheet.employee_id == f.employee_id)
    if f.matched is not None:
        where.append(
            Timesheet.employee_id.is_not(None) if f.matched else Timesheet.employee_id.is_(None)
        )
    if f.sender:
        where.append(_contains(Submission.sender_email, f.sender.strip()))
    if f.q:
        text = f.q.strip()
        where.append(
            or_(
                _contains(Timesheet.extracted_name, text),
                _contains(Timesheet.extracted_code, text),
                _contains(Employee.full_name, text),
                _contains(Employee.employee_code, text),
            )
        )

    # A week overlaps [date_from, date_to] when it starts at most 6 days before
    # date_from and no later than date_to.
    if f.date_from is not None:
        where.append(Timesheet.week_start >= f.date_from - timedelta(days=6))
    if f.date_to is not None:
        where.append(Timesheet.week_start <= f.date_to)
    if f.received_from is not None:
        where.append(Submission.received_at >= _start_of_day(f.received_from))
    if f.received_to is not None:
        where.append(Submission.received_at < _start_of_day(f.received_to + timedelta(days=1)))
    if f.min_confidence is not None:
        where.append(Timesheet.confidence >= f.min_confidence)
    if f.max_confidence is not None:
        where.append(Timesheet.confidence <= f.max_confidence)
    return where


def _order_by(f: TimesheetFilters) -> list[Any]:
    key: Any = {
        TimesheetSort.RECEIVED: Submission.received_at,
        TimesheetSort.WEEK: Timesheet.week_start,
        TimesheetSort.EMPLOYEE: func.lower(
            func.coalesce(Employee.full_name, Timesheet.extracted_name, "")
        ),
        TimesheetSort.HOURS: Timesheet.total_hours,
        TimesheetSort.GROSS: Timesheet.gross_amount,
        TimesheetSort.CONFIDENCE: Timesheet.confidence,
        TimesheetSort.SEVERITY: SEVERITY_RANK,
    }[f.sort]
    first = key.asc() if f.order == SortOrder.ASC else key.desc()
    # Empty values (no week, not priced, ...) always go last; then newest first.
    return [first.nulls_last(), Submission.received_at.desc(), Timesheet.id]


class TimesheetRepository(BaseRepository[Timesheet]):
    model = Timesheet

    async def search(
        self, filters: TimesheetFilters, *, page: int, size: int
    ) -> tuple[Sequence[Timesheet], int]:
        query = (
            select(Timesheet)
            .join(Submission, Submission.id == Timesheet.submission_id)
            .outerjoin(Employee, Employee.id == Timesheet.employee_id)
            .where(*_conditions(filters))
            .order_by(*_order_by(filters))
        )
        return await self.paginate(query, page=page, size=size)
