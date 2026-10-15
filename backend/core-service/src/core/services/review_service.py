"""What reviewers do to a timesheet: fix hours, pick the employee, approve, reject.

Every change re-runs the pay rules and duplicate checks, and writes an audit event."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.audit import record_event
from src.core.services.employee_matcher import MatchResult, apply_match
from src.core.services.pay_rules import recalculate, rules_from_company
from src.core.services.timesheet_validation import validate_duplicates
from src.data.models import Company, Document, Employee, Timesheet, TimesheetEntry
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.review import EntriesUpdate
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
        "long_day"
    }
)


def _totals(timesheet: Timesheet) -> dict[str, float]:
    return {
        "regular": float(timesheet.regular_hours),
        "overtime": float(timesheet.overtime_hours),
        "double_time": float(timesheet.double_time_hours),
        "holiday": float(timesheet.holiday_hours),
    }


def _refresh_entry_flags(timesheet: Timesheet) -> None:
    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in ENTRY_FLAG_CODES
    ]
    total = sum((e.hours for e in timesheet.entries), Decimal("0"))
    if not timesheet.entries:
        flags.append({"code": "no_entries", "message": "The timesheet has no hours."})
    elif timesheet.stated_total is not None and timesheet.stated_total != total:
        flags.append(
            {
                "code": "total_mismatch",
                "message": f"Sheet says {timesheet.stated_total} h; the days add up to {total} h.",
            }
        )
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

    async def _save(self, timesheet: Timesheet) -> Timesheet:
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

        # Delete the old days first: same dates would clash with the unique constraint.
        timesheet.entries.clear()
        await self.session.flush()
        timesheet.entries.extend(
            TimesheetEntry(
                work_date=e.work_date,
                hours=e.hours,
                double_time_marked=e.double_time_marked,
                is_holiday=e.is_holiday,
                note=e.note,
            )
            for e in sorted(data.entries, key=lambda e: e.work_date)
        )
        if data.entries:
            company = await self._company(timesheet)
            first_day = min(e.work_date for e in data.entries)
            timesheet.week_start = start_of_week(first_day, company.week_start if company else 0)

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
        return await self._save(timesheet)

    async def match_employee(
        self, timesheet_id: uuid.UUID, employee_id: uuid.UUID, actor: Principal
    ) -> Timesheet:
        timesheet = await self._get(timesheet_id)
        self._ensure_editable(timesheet)

        employee = await self.session.get(Employee, employee_id)
        if employee is None or not employee.is_active:
            raise ValidationFailedError("Employee not found or inactive.")
        if timesheet.company_id is not None and employee.company_id != timesheet.company_id:
            raise ValidationFailedError("This employee belongs to another company.")

        timesheet.company_id = employee.company_id  # sets the company if it was unknown
        apply_match(timesheet, MatchResult(employee.id, "manual"))
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
        return await self._save(timesheet)

    async def approve(
        self, timesheet_id: uuid.UUID, notes: str | None, actor: Principal
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
            details={"notes": notes, "open_flags": [f.get("code") for f in timesheet.flags or []]},
        )
        return await self._save(timesheet)

    async def reject(self, timesheet_id: uuid.UUID, reason: str, actor: Principal) -> Timesheet:
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
            details={"reason": reason},
        )
        return await self._save(timesheet)
