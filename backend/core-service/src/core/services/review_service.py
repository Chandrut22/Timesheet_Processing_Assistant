"""What reviewers do to a timesheet: fix hours, pick the employee, approve, reject.

Every change re-runs the pay rules and duplicate checks, and writes an audit event."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.flags import Severity
from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import AppError, ConflictError, NotFoundError, ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.activity_log import refresh_state
from src.core.services.audit import record_event
from src.core.services.employee_matcher import MatchResult, apply_match, to_record
from src.core.services.pay_rules import recalculate, rules_from_company
from src.core.services.timesheet_builder import conflicting_hours_flag
from src.core.services.timesheet_validation import (
    check_assignment,
    lock_employee_weeks,
    other_paid_timesheet,
    validate_duplicates,
)
from src.data.models import Company, Document, Employee, Timesheet, TimesheetEntry
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.review import BulkItemResult, BulkResult, EntriesUpdate
from src.utils.dates import start_of_week

# Flags about the extracted days: stale once a reviewer sets the days by hand.
ENTRY_FLAG_CODES = frozenset(
    {
        "duplicate_day",
        "day_over_24",
        "dates_assumed",
        "undated_days",
        "no_entries",
        "total_mismatch",
        "conflicting_hours",
    }
)
# Company flags raised at extraction: settled once a reviewer picks the employee.
COMPANY_FLAG_CODES = frozenset({"company_mismatch", "company_from_sheet", "company_guessed"})


def _totals(timesheet: Timesheet) -> dict[str, float | None]:
    def money(value: Decimal | None) -> float | None:
        return None if value is None else float(value)

    return {
        "regular": float(timesheet.regular_hours),
        "overtime": float(timesheet.overtime_hours),
        "double_time": float(timesheet.double_time_hours),
        "holiday": float(timesheet.holiday_hours),
        "regular_amount": money(timesheet.regular_amount),
        "overtime_amount": money(timesheet.overtime_amount),
        "double_time_amount": money(timesheet.double_time_amount),
        "holiday_amount": money(timesheet.holiday_amount),
    }


def is_priced(timesheet: Timesheet) -> bool:
    """All four amounts known (the generated gross_amount is only read after a refresh)."""
    return None not in (
        timesheet.regular_amount,
        timesheet.overtime_amount,
        timesheet.double_time_amount,
        timesheet.holiday_amount,
    )


def _refresh_entry_flags(timesheet: Timesheet) -> None:
    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in ENTRY_FLAG_CODES
    ]
    total = sum((e.hours for e in timesheet.entries), Decimal("0"))
    if not timesheet.entries:
        flags.append({"code": "no_entries", "message": "The timesheet has no hours."})
    else:
        if timesheet.stated_total is not None and timesheet.stated_total != total:
            flags.append(
                {
                    "code": "total_mismatch",
                    "message": f"Sheet says {timesheet.stated_total} h; "
                    f"the days add up to {total} h.",
                }
            )
        # The reviewer's days are now "the attachment": compare with the email again.
        conflict = conflicting_hours_flag(timesheet.email_stated_total, total)
        if conflict:
            flags.append(conflict)
    timesheet.flags = flags


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get(self, timesheet_id: uuid.UUID) -> Timesheet:
        timesheet = await self.session.get(Timesheet, timesheet_id)
        if timesheet is None:
            raise NotFoundError("Timesheet not found.")
        return timesheet

    @staticmethod
    def _ensure_editable(timesheet: Timesheet) -> None:
        if timesheet.status == TimesheetStatus.EXPORTED:
            raise ConflictError("This timesheet was already exported to payroll and cannot change.")
        if timesheet.status == TimesheetStatus.SUPERSEDED:
            raise ConflictError(
                "This is an older version, replaced when the email was reprocessed. "
                "Open the current version instead."
            )

    async def _company(self, timesheet: Timesheet) -> Company | None:
        if timesheet.company_id is None:
            return None
        return await self.session.get(Company, timesheet.company_id)

    async def _recompute(self, timesheet: Timesheet) -> None:
        """Pay rules + duplicate checks, after any change."""
        company = await self._company(timesheet)
        holidays = await HolidayRepository(self.session).dates_for(timesheet.company_id)
        recalculate(
            timesheet, rules_from_company(company), holidays, default_rules_used=company is None
        )
        employee = (
            await self.session.get(Employee, timesheet.employee_id)
            if timesheet.employee_id
            else None
        )
        if employee is not None:
            check_assignment(timesheet, employee.assignment_start, employee.assignment_end)
        await self.session.flush()
        document = (
            await self.session.get(Document, timesheet.document_id)
            if timesheet.document_id
            else None
        )
        await validate_duplicates(self.session, timesheet, document)

    @staticmethod
    def _back_to_review(timesheet: Timesheet) -> None:
        if timesheet.status == TimesheetStatus.APPROVED:
            timesheet.status = TimesheetStatus.NEEDS_REVIEW
            timesheet.reviewed_by_id = None
            timesheet.reviewed_by_name = None
            timesheet.reviewed_at = None

    async def _save(self, timesheet: Timesheet, actor: Principal) -> Timesheet:
        # The email's state follows its timesheets (awaiting review / approved / rejected).
        await refresh_state(self.session, timesheet.submission_id, actor=actor)
        await self.session.commit()
        await self.session.refresh(timesheet)
        return timesheet

    # --- actions ---------------------------------------------------------------

    async def update_entries(
        self, timesheet_id: uuid.UUID, data: EntriesUpdate, actor: Principal
    ) -> Timesheet:
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        before = _totals(timesheet)
        company = await self._company(timesheet)
        week_start_day = company.week_start if company else 0
        weeks = sorted({start_of_week(e.work_date, week_start_day) for e in data.entries})
        if len(weeks) > 1:
            raise ValidationFailedError(
                "All days must be in one week (a timesheet is paid per week). These days "
                f"fall in the weeks starting {', '.join(str(w) for w in weeks)}."
            )

        # Delete the old days first: same dates would clash with the unique constraint.
        timesheet.entries.clear()
        await self.session.flush()
        timesheet.entries.extend(
            TimesheetEntry(
                work_date=e.work_date,
                hours=e.hours,
                double_time_marked=e.double_time_marked,
                is_holiday=e.is_holiday,  # calendar holidays are added by recalculate()
                sheet_holiday=e.is_holiday,  # marked by the reviewer
                note=e.note,
            )
            for e in sorted(data.entries, key=lambda e: e.work_date)
        )
        if weeks:
            timesheet.week_start = weeks[0]

        _refresh_entry_flags(timesheet)
        await self._recompute(timesheet)
        self._back_to_review(timesheet)

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="entries_edited",
            actor=actor,
            details={"before": before, "after": _totals(timesheet), "days": len(data.entries)},
        )
        return await self._save(timesheet, actor)

    async def match_employee(
        self, timesheet_id: uuid.UUID, employee_id: uuid.UUID, actor: Principal
    ) -> Timesheet:
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)

        employee = await self.session.get(Employee, employee_id)
        if employee is None or not employee.is_active:
            raise ValidationFailedError("Employee not found or inactive.")
        company_in_doubt = any(f.get("code") in COMPANY_FLAG_CODES for f in timesheet.flags or [])
        if (
            timesheet.company_id is not None
            and employee.company_id != timesheet.company_id
            and not company_in_doubt  # sheet and sender disagreed: the reviewer decides
        ):
            raise ValidationFailedError("This employee belongs to another company.")

        timesheet.company_id = employee.company_id  # sets the company if it was unknown
        timesheet.flags = [
            f for f in (timesheet.flags or []) if f.get("code") not in COMPANY_FLAG_CODES
        ]
        apply_match(timesheet, MatchResult(employee.id, "manual"), matched=to_record(employee))
        await self._recompute(timesheet)
        self._back_to_review(timesheet)

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="employee_matched",
            actor=actor,
            details={"employee_id": str(employee.id), "employee_code": employee.employee_code},
        )
        return await self._save(timesheet, actor)

    async def recalculate(self, timesheet_id: uuid.UUID, actor: Principal) -> Timesheet:
        """Run the pay rules again with the company's CURRENT rules, rates and holidays,
        e.g. after a missing rate was added. An approved timesheet whose hours or pay
        change goes back to review."""
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        before = _totals(timesheet)
        await self._recompute(timesheet)
        after = _totals(timesheet)
        if after != before:
            self._back_to_review(timesheet)

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="recalculated",
            actor=actor,
            details={"before": before, "after": after, "changed": after != before},
        )
        return await self._save(timesheet, actor)

    async def approve(
        self,
        timesheet_id: uuid.UUID,
        notes: str | None,
        actor: Principal,
        *,
        bulk: bool = False,
    ) -> Timesheet:
        timesheet = await self._get(timesheet_id)
        if timesheet.status not in (TimesheetStatus.NEEDS_REVIEW, TimesheetStatus.REJECTED):
            raise ConflictError(
                f"Only timesheets in review can be approved (this one is {timesheet.status})."
            )
        if timesheet.employee_id is None:
            raise ValidationFailedError("Match an employee before approving.")
        if not timesheet.entries:
            raise ValidationFailedError("A timesheet without hours cannot be approved.")
        if not is_priced(timesheet):
            raise ValidationFailedError(
                "The pay for this timesheet could not be calculated (a company rate is "
                "missing). Add the rate to the company, recalculate, then approve."
            )
        # One paid timesheet per employee and week: never approve a second one.
        await lock_employee_weeks(self.session, [(timesheet.employee_id, timesheet.week_start)])
        other = await other_paid_timesheet(self.session, timesheet)
        if other is not None:
            raise ConflictError(
                f"Another timesheet for this employee and the week of {timesheet.week_start} "
                f"is already {other.status} ({other.id}). Only one can be paid: reject one "
                "of them, or put all the hours on one timesheet."
            )

        timesheet.status = TimesheetStatus.APPROVED
        timesheet.reviewed_by_id = actor.id
        timesheet.reviewed_by_name = actor.name
        timesheet.reviewed_at = datetime.now(UTC)
        if notes:
            timesheet.notes = notes

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="approved",
            actor=actor,
            details={
                "notes": notes,
                "open_flags": [f.get("code") for f in timesheet.flags or []],
                "bulk": bulk,
            },
        )
        return await self._save(timesheet, actor)

    async def reject(
        self, timesheet_id: uuid.UUID, reason: str, actor: Principal, *, bulk: bool = False
    ) -> Timesheet:
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        if timesheet.status == TimesheetStatus.REJECTED:
            raise ConflictError("This timesheet is already rejected.")

        timesheet.status = TimesheetStatus.REJECTED
        timesheet.notes = reason
        timesheet.reviewed_by_id = actor.id
        timesheet.reviewed_by_name = actor.name
        timesheet.reviewed_at = datetime.now(UTC)

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="rejected",
            actor=actor,
            details={"reason": reason, "bulk": bulk},
        )
        return await self._save(timesheet, actor)

    # --- bulk ----------------------------------------------------------------------
    # Each timesheet goes through the same checks as a single approve / reject and is
    # committed on its own, so one bad item is reported and the rest still go through.

    async def bulk_approve(
        self,
        timesheet_ids: list[uuid.UUID],
        notes: str | None,
        actor: Principal,
        *,
        include_high_severity: bool = False,
    ) -> BulkResult:
        results: list[BulkItemResult] = []
        for timesheet_id in timesheet_ids:
            try:
                if not include_high_severity:
                    await self._refuse_high_severity(timesheet_id)
                timesheet = await self.approve(timesheet_id, notes, actor, bulk=True)
                results.append(
                    BulkItemResult(timesheet_id=timesheet_id, ok=True, status=timesheet.status)
                )
            except AppError as exc:
                results.append(await self._failed(timesheet_id, exc))
        return _summary(results)

    async def bulk_reject(
        self, timesheet_ids: list[uuid.UUID], reason: str, actor: Principal
    ) -> BulkResult:
        results: list[BulkItemResult] = []
        for timesheet_id in timesheet_ids:
            try:
                timesheet = await self.reject(timesheet_id, reason, actor, bulk=True)
                results.append(
                    BulkItemResult(timesheet_id=timesheet_id, ok=True, status=timesheet.status)
                )
            except AppError as exc:
                results.append(await self._failed(timesheet_id, exc))
        return _summary(results)

    async def _refuse_high_severity(self, timesheet_id: uuid.UUID) -> None:
        timesheet = await self._get(timesheet_id)
        if timesheet.severity == Severity.HIGH and timesheet.status in (
            TimesheetStatus.NEEDS_REVIEW,
            TimesheetStatus.REJECTED,
        ):
            codes = ", ".join(
                str(f.get("code")) for f in timesheet.flags or [] if f.get("severity") == "high"
            )
            raise ValidationFailedError(
                f"Has high-severity flags ({codes}). Open it and approve it on its own."
            )

    async def _failed(self, timesheet_id: uuid.UUID, exc: AppError) -> BulkItemResult:
        await self.session.rollback()  # drop anything half-done for this item
        timesheet = await self.session.get(Timesheet, timesheet_id, populate_existing=True)
        return BulkItemResult(
            timesheet_id=timesheet_id,
            ok=False,
            status=timesheet.status if timesheet is not None else None,
            error=exc.message,
        )


def _summary(results: list[BulkItemResult]) -> BulkResult:
    succeeded = sum(1 for r in results if r.ok)
    return BulkResult(
        requested=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
