"""What reviewers do to a timesheet: fix hours, pick the employee, approve, reject,
and roll back to an earlier version.

Every change re-runs the pay rules and duplicate checks, and writes an audit event.
A change of the data (days, employee, week, pay) first keeps the timesheet as it was
in timesheet_versions and raises its version (see version_history.py)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.flags import Severity
from src.constants.timesheet_status import TimesheetChange, TimesheetStatus
from src.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from src.core.rbac.principal import Principal
from src.core.services.activity_log import refresh_state
from src.core.services.audit import record_event
from src.core.services.employee_matcher import MatchResult, apply_match, to_record
from src.core.services.pay_rules import (
    WEEK_ASSUMED_FLAG,
    WEEKLY_TOTAL_FLAG,
    has_hours,
    recalculate,
    rules_from_company,
    weekly_total,
)
from src.core.services.timesheet_builder import conflicting_hours_flag
from src.core.services.timesheet_validation import (
    check_assignment,
    lock_employee_weeks,
    other_paid_timesheet,
    validate_duplicates,
)
from src.core.services.version_history import (
    save_version,
    switch_to_version,
    take_snapshot,
)
from src.data.models import (
    Company,
    Document,
    Employee,
    Timesheet,
    TimesheetEntry,
    TimesheetVersion,
)
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.review import BulkItemResult, BulkResult, EntriesUpdate
from src.utils.dates import start_of_week, weekday_name

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
        # the reviewer has checked the days against the original
        "overlap_disagreement",
        # A weekly-total timesheet becomes a normal one once the reviewer enters days.
        WEEKLY_TOTAL_FLAG,
        WEEK_ASSUMED_FLAG,
    }
)
# Company flags raised at extraction: settled once a reviewer picks the employee.
COMPANY_FLAG_CODES = frozenset(
    {"company_mismatch", "company_from_sheet", "company_guessed"}
)


async def _new_version_if_asked(
    session: AsyncSession,
    timesheet: Timesheet,
    before: dict[str, Any],
    change: TimesheetChange,
    actor: Principal,
    asked: bool,
) -> bool:
    """A reviewer's edit is saved in the current version. Only when they click "Create
    as new version" is the timesheet as it was kept as a version (this becomes the
    next one). A reprocess always makes a version (reprocess.py)."""
    if not asked:
        return False
    await save_version(session, timesheet, before, change, actor=actor, force=True)
    return True


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
    """All four amounts known (the generated gross_amount is only read after a
    refresh)."""
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
                    "message": f"Sheet says {timesheet.stated_total} h; the days add "
                    f"up to {total} h.",
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
            raise ConflictError(
                "This timesheet was already exported to payroll and cannot change."
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
            timesheet,
            rules_from_company(company),
            holidays,
            default_rules_used=company is None,
        )
        employee = (
            await self.session.get(Employee, timesheet.employee_id)
            if timesheet.employee_id
            else None
        )
        if employee is not None:
            check_assignment(
                timesheet, employee.assignment_start, employee.assignment_end
            )
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
        # The email's state follows its timesheets (awaiting review / approved /
        # rejected).
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
        snap = take_snapshot(timesheet)
        company = await self._company(timesheet)
        week_start_day = company.week_start if company else 0
        weeks = sorted(
            {start_of_week(e.work_date, week_start_day) for e in data.entries}
        )
        if len(weeks) > 1:
            raise ValidationFailedError(
                "All days must be in one week (a timesheet is paid per week). These "
                f"days fall in the weeks starting {', '.join(str(w) for w in weeks)}."
            )

        timesheet.entries = [
            TimesheetEntry(
                work_date=e.work_date,
                hours=e.hours,
                double_time_marked=e.double_time_marked,
                is_holiday=e.is_holiday,  # calendar holidays are added by recalculate()
                sheet_holiday=e.is_holiday,  # marked by the reviewer
                note=e.note,
            )
            for e in sorted(data.entries, key=lambda e: e.work_date)
        ]
        if weeks:
            timesheet.week_start = weeks[0]

        _refresh_entry_flags(timesheet)
        await self._recompute(timesheet)
        self._back_to_review(timesheet)
        made = await _new_version_if_asked(
            self.session,
            timesheet,
            snap,
            TimesheetChange.ENTRIES_EDITED,
            actor,
            data.new_version,
        )

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="entries_edited",
            actor=actor,
            details={
                "before": before,
                "after": _totals(timesheet),
                "days": len(data.entries),
                "version": timesheet.version,
                "new_version": made,
            },
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
        company_in_doubt = any(
            f.get("code") in COMPANY_FLAG_CODES for f in timesheet.flags or []
        )
        if (
            timesheet.company_id is not None
            and employee.company_id != timesheet.company_id
            and not company_in_doubt  # sheet and sender disagreed: the reviewer decides
        ):
            raise ValidationFailedError("This employee belongs to another company.")

        timesheet.company_id = employee.company_id  # sets the company if it was unknown
        timesheet.flags = [
            f
            for f in (timesheet.flags or [])
            if f.get("code") not in COMPANY_FLAG_CODES
        ]
        apply_match(
            timesheet, MatchResult(employee.id, "manual"), matched=to_record(employee)
        )
        await self._recompute(timesheet)
        self._back_to_review(timesheet)  # saved in the current version

        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="employee_matched",
            actor=actor,
            details={
                "employee_id": str(employee.id),
                "employee_code": employee.employee_code,
            },
        )
        return await self._save(timesheet, actor)

    async def set_week(
        self,
        timesheet_id: uuid.UUID,
        week_start: date,
        actor: Principal,
        *,
        new_version: bool = False,
    ) -> Timesheet:
        """Move a weekly-total timesheet (no days) to another week, e.g. when the week
        was assumed. A timesheet with days moves with its days (update_entries)."""
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        if weekly_total(timesheet) is None:
            raise ValidationFailedError(
                "Only a timesheet with a weekly total and no days can be moved to "
                "another week. For one with days, change the days."
            )
        company = await self._company(timesheet)
        week_start_day = company.week_start if company else 0
        if start_of_week(week_start, week_start_day) != week_start:
            raise ValidationFailedError(
                f"Weeks start on {weekday_name(week_start_day)} for this company: pick "
                f"a {weekday_name(week_start_day)}."
            )
        before = timesheet.week_start
        snap = take_snapshot(timesheet)
        timesheet.week_start = week_start
        timesheet.flags = [
            f for f in timesheet.flags or [] if f.get("code") != WEEK_ASSUMED_FLAG
        ]  # the reviewer chose it: no longer an assumption
        await self._recompute(
            timesheet
        )  # pay, and the duplicate check for the new week
        self._back_to_review(timesheet)
        made = await _new_version_if_asked(
            self.session,
            timesheet,
            snap,
            TimesheetChange.WEEK_CHANGED,
            actor,
            new_version,
        )
        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="week_changed",
            actor=actor,
            details={
                "before": str(before) if before else None,
                "after": str(week_start),
                "version": timesheet.version,
                "new_version": made,
            },
        )
        return await self._save(timesheet, actor)

    async def recalculate(self, timesheet_id: uuid.UUID, actor: Principal) -> Timesheet:
        """Run the pay rules again with the company's CURRENT rules, rates and holidays,
        e.g. after a missing rate was added. An approved timesheet whose hours or pay
        change goes back to review."""
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        before = _totals(timesheet)
        await self._recompute(timesheet)  # saved in the current version
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
        if timesheet.status not in (
            TimesheetStatus.NEEDS_REVIEW,
            TimesheetStatus.REJECTED,
        ):
            raise ConflictError(
                "Only timesheets in review can be approved (this one is "
                f"{timesheet.status})."
            )
        if timesheet.employee_id is None:
            raise ValidationFailedError("Match an employee before approving.")
        if not has_hours(timesheet):  # days, or a weekly total
            raise ValidationFailedError("A timesheet without hours cannot be approved.")
        if not is_priced(timesheet):
            raise ValidationFailedError(
                "The pay for this timesheet could not be calculated (a company rate is "
                "missing). Add the rate to the company, recalculate, then approve."
            )
        # One paid timesheet per employee and week: never approve a second one.
        await lock_employee_weeks(
            self.session, [(timesheet.employee_id, timesheet.week_start)]
        )
        other = await other_paid_timesheet(self.session, timesheet)
        if other is not None:
            raise ConflictError(
                "Another timesheet for this employee and the week of "
                f"{timesheet.week_start} is already {other.status} ({other.id}). Only "
                "one can be paid: reject one of them, or put all the hours on one "
                "timesheet."
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
        self,
        timesheet_id: uuid.UUID,
        reason: str,
        actor: Principal,
        *,
        bulk: bool = False,
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

    # --- versions
    # ----------------------------------------------------------------------

    async def versions(
        self, timesheet_id: uuid.UUID
    ) -> tuple[Timesheet, list[TimesheetVersion]]:
        """The timesheet and its saved versions, oldest first."""
        timesheet = await self._get(timesheet_id)
        rows = await self.session.scalars(
            select(TimesheetVersion)
            .where(TimesheetVersion.timesheet_id == timesheet_id)
            .order_by(TimesheetVersion.version)
        )
        return timesheet, list(rows.all())

    async def version(self, timesheet_id: uuid.UUID, number: int) -> TimesheetVersion:
        found = await self.session.scalar(
            select(TimesheetVersion).where(
                TimesheetVersion.timesheet_id == timesheet_id,
                TimesheetVersion.version == number,
            )
        )
        if found is None:
            raise NotFoundError(f"Version {number} of this timesheet was not found.")
        return found

    async def restore_version(
        self, timesheet_id: uuid.UUID, number: int, reason: str | None, actor: Principal
    ) -> Timesheet:
        """Go back to version `number`: the timesheet gets its days, employee, week, pay
        and flags, and its number (no new version is made). What it had is kept under
        its own number, so you can switch back. It goes back to review. Not possible
        once exported to payroll."""
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)
        if number == timesheet.version:
            raise ConflictError(f"Version {number} is already the current version.")
        saved = await self.version(timesheet_id, number)
        current = timesheet.version

        await switch_to_version(
            self.session, timesheet, saved, actor=actor, reason=reason
        )
        timesheet.status = (
            TimesheetStatus.NEEDS_REVIEW
        )  # a person checks the restored data
        timesheet.reviewed_by_id = None
        timesheet.reviewed_by_name = None
        timesheet.reviewed_at = None
        await self.session.flush()
        # The pay stays as it was in that version; only the duplicate check is redone,
        # because other timesheets may have changed since.
        document = (
            await self.session.get(Document, timesheet.document_id)
            if timesheet.document_id
            else None
        )
        await validate_duplicates(self.session, timesheet, document)
        record_event(
            self.session,
            entity_type="timesheet",
            entity_id=timesheet.id,
            action="rolled_back",
            actor=actor,
            details={
                "restored_version": number,
                "from_version": current,
                "reason": reason,
            },
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
                    BulkItemResult(
                        timesheet_id=timesheet_id, ok=True, status=timesheet.status
                    )
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
                    BulkItemResult(
                        timesheet_id=timesheet_id, ok=True, status=timesheet.status
                    )
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
                str(f.get("code"))
                for f in timesheet.flags or []
                if f.get("severity") == "high"
            )
            raise ValidationFailedError(
                f"Has high-severity flags ({codes}). Open it and approve it on its own."
            )

    async def _failed(self, timesheet_id: uuid.UUID, exc: AppError) -> BulkItemResult:
        await self.session.rollback()  # drop anything half-done for this item
        timesheet = await self.session.get(
            Timesheet, timesheet_id, populate_existing=True
        )
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
