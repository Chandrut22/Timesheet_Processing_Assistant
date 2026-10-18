"""Payroll export: the approved timesheets of one client company for one week
become one CSV payroll sheet, which Company A sends back to the client.

Exported timesheets are locked (status "exported"): they can no longer be edited,
re-approved or reprocessed, and they never go into a second payroll sheet."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.activity_log import refresh_state
from src.core.services.audit import record_event
from src.core.services.payroll_csv import (
    ExportRow,
    ExportTotals,
    build_csv,
    export_filename,
    totals,
    week_end,
)
from src.data.models import Company, Employee, ExportBatch, Timesheet
from src.data.repositories.export_repository import ExportRepository
from src.utils.dates import start_of_week

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def to_row(timesheet: Timesheet, employee: Employee) -> ExportRow:
    return ExportRow(
        timesheet_id=timesheet.id,
        employee_id=employee.id,
        employee_code=employee.employee_code,
        employee_name=employee.full_name,
        regular=timesheet.regular_hours,
        overtime=timesheet.overtime_hours,
        double_time=timesheet.double_time_hours,
        holiday=timesheet.holiday_hours,
        approved_by=timesheet.reviewed_by_name,
        approved_at=timesheet.reviewed_at,
        currency=timesheet.currency,
        hourly_rate=timesheet.hourly_rate,
        overtime_rate=timesheet.overtime_rate,
        double_time_rate=timesheet.double_time_rate,
        holiday_rate=timesheet.holiday_rate,
        regular_amount=timesheet.regular_amount,
        overtime_amount=timesheet.overtime_amount,
        double_time_amount=timesheet.double_time_amount,
        holiday_amount=timesheet.holiday_amount,
    )


def duplicate_problems(
    pairs: list[tuple[Timesheet, Employee]], exported: set[uuid.UUID]
) -> list[str]:
    """Pure: an employee must be paid at most once per week. Returns one message per
    employee with two approved timesheets, or one already in an earlier payroll sheet."""
    seen: dict[uuid.UUID, list[Timesheet]] = {}
    names: dict[uuid.UUID, str] = {}
    for timesheet, employee in pairs:
        seen.setdefault(employee.id, []).append(timesheet)
        names[employee.id] = f"{employee.full_name} ({employee.employee_code})"
    problems: list[str] = []
    for employee_id, sheets in seen.items():
        if len(sheets) > 1:
            problems.append(
                f"{names[employee_id]} has {len(sheets)} approved timesheets for this week "
                f"({', '.join(str(t.id) for t in sheets)}). Reject all but one."
            )
        if employee_id in exported:
            problems.append(
                f"{names[employee_id]} was already paid for this week in an earlier payroll "
                "sheet. Reject the new timesheet, or correct the earlier payroll by hand."
            )
    return problems


class ExportPreviewResult:
    """What an export would contain right now (nothing is changed)."""

    def __init__(
        self,
        company: Company,
        week_start: date,
        rows: list[ExportRow],
        status_counts: dict[str, int],
        problems: list[str] | None = None,
    ) -> None:
        self.company = company
        self.week_start = week_start
        self.rows = rows
        self.totals: ExportTotals = totals(rows)
        self.pending_review = status_counts.get(TimesheetStatus.NEEDS_REVIEW, 0)
        self.rejected = status_counts.get(TimesheetStatus.REJECTED, 0)
        self.already_exported = status_counts.get(TimesheetStatus.EXPORTED, 0)
        self.problems = problems or []  # duplicates that block the export


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.exports = ExportRepository(session)

    async def _company(self, company_id: uuid.UUID) -> Company:
        company = await self.session.get(Company, company_id)
        if company is None:
            raise NotFoundError("Company not found.")
        return company

    @staticmethod
    def _check_week(company: Company, week_start: date) -> None:
        """Timesheets are stored by the company's own week, so week_start must be its first day."""
        if week_start.weekday() != company.week_start:
            first = start_of_week(week_start, company.week_start)
            raise ValidationFailedError(
                f"{company.name}'s week starts on {DAY_NAMES[company.week_start]}, "
                f"but {week_start} is a {DAY_NAMES[week_start.weekday()]}. "
                f"Use {first} for that week."
            )

    async def get(self, batch_id: uuid.UUID) -> ExportBatch:
        batch = await self.exports.get(batch_id)
        if batch is None:
            raise NotFoundError("Export not found.")
        return batch

    async def preview(self, company_id: uuid.UUID, week_start: date) -> ExportPreviewResult:
        company = await self._company(company_id)
        self._check_week(company, week_start)
        pairs = await self.exports.ready_to_export(company_id, week_start)
        counts = await self.exports.count_by_status(company_id, week_start)
        problems = await self._duplicates(pairs, week_start)
        rows = [to_row(t, e) for t, e in pairs]
        return ExportPreviewResult(company, week_start, rows, counts, problems)

    async def _duplicates(
        self, pairs: list[tuple[Timesheet, Employee]], week_start: date
    ) -> list[str]:
        exported = await self.exports.exported_employees(list({e.id for _, e in pairs}), week_start)
        return duplicate_problems(pairs, exported)

    async def create(
        self,
        company_id: uuid.UUID,
        week_start: date,
        actor: Principal,
        *,
        allow_pending: bool = False,
    ) -> ExportBatch:
        company = await self._company(company_id)
        self._check_week(company, week_start)

        counts = await self.exports.count_by_status(company_id, week_start)
        pending = counts.get(TimesheetStatus.NEEDS_REVIEW, 0)
        if pending and not allow_pending:
            raise ConflictError(
                f"{pending} timesheet(s) for this week still need review. Review them first, "
                "or export anyway with allow_pending=true (they can go in a later export)."
            )

        pairs = await self.exports.ready_to_export(company_id, week_start, lock=True)
        if not pairs:
            raise ConflictError("No approved timesheets left to export for this company and week.")
        problems = await self._duplicates(pairs, week_start)
        if problems:
            raise ConflictError(
                "An employee would be paid twice for this week: " + " ".join(problems[:5])
            )

        rows = [to_row(t, e) for t, e in pairs]
        unpriced = [r for r in rows if not r.is_priced]
        if unpriced:
            names = ", ".join(sorted(r.employee_name for r in unpriced)[:5])
            raise ConflictError(
                f"{len(unpriced)} approved timesheet(s) have no pay amount ({names}): a company "
                "rate is missing. Add the rate to the company, recalculate those timesheets, "
                "then export again."
            )
        sums = totals(rows)
        batch_id = uuid.uuid4()
        batch = ExportBatch(
            id=batch_id,
            company_id=company.id,
            company_name=company.name,
            week_start=week_start,
            week_end=week_end(week_start),
            row_count=sums.rows,
            regular_hours=sums.regular,
            overtime_hours=sums.overtime,
            double_time_hours=sums.double_time,
            holiday_hours=sums.holiday,
            currency=company.currency,
            regular_amount=sums.regular_amount,
            overtime_amount=sums.overtime_amount,
            double_time_amount=sums.double_time_amount,
            holiday_amount=sums.holiday_amount,
            filename=export_filename(company.name, week_start, batch_id),
            csv_content=build_csv(company.name, week_start, rows),
            created_by_id=actor.id,
            created_by_name=actor.name,
        )
        await self.exports.add(batch)

        now = datetime.now(UTC)
        for timesheet, _ in pairs:
            timesheet.status = TimesheetStatus.EXPORTED
            timesheet.exported_at = now
            timesheet.export_batch_id = batch.id
            record_event(
                self.session,
                entity_type="timesheet",
                entity_id=timesheet.id,
                action="exported",
                actor=actor,
                details={"export_batch_id": str(batch.id)},
            )
        record_event(
            self.session,
            entity_type="export",
            entity_id=batch.id,
            action="created",
            actor=actor,
            details={
                "company_id": str(company.id),
                "week_start": week_start.isoformat(),
                "rows": sums.rows,
                "gross_amount": str(sums.gross),
                "currency": company.currency,
                "pending_review_left_out": pending,
            },
        )
        for submission_id in {t.submission_id for t, _ in pairs}:
            await refresh_state(self.session, submission_id, actor=actor)
        await self.session.commit()
        await self.session.refresh(batch)
        return batch
