"""Checks that need the database (duplicates), and the auto-approve decision."""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import DocumentStatus, TimesheetStatus
from src.data.models import Document, Timesheet

# Flags this module owns: removed and recomputed on every validation.
VALIDATION_FLAG_CODES = frozenset({"duplicate_file", "duplicate_week"})

# Flags that are only information and do not stop auto-approval.
NON_BLOCKING_FLAGS = frozenset({"holiday_worked"})

LIVE_STATUSES = (TimesheetStatus.NEEDS_REVIEW, TimesheetStatus.APPROVED, TimesheetStatus.EXPORTED)


async def validate_duplicates(
    session: AsyncSession, timesheet: Timesheet, document: Document | None
) -> None:
    """Flag a file seen before, or a second timesheet for the same person and week.
    Call after the timesheet was flushed (it needs its id)."""
    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in VALIDATION_FLAG_CODES
    ]

    if document is not None:
        earlier = await session.scalar(
            select(Document.filename)
            .where(
                Document.sha256 == document.sha256,
                Document.id != document.id,
                Document.status == DocumentStatus.PARSED,
            )
            .limit(1)
        )
        if earlier is not None:
            flags.append(
                {
                    "code": "duplicate_file",
                    "message": f"This exact file was already processed (as '{earlier}').",
                }
            )

    if timesheet.employee_id is not None and timesheet.week_start is not None:
        other = await session.scalar(
            select(Timesheet.id)
            .where(
                Timesheet.employee_id == timesheet.employee_id,
                Timesheet.week_start == timesheet.week_start,
                Timesheet.id != timesheet.id,
                Timesheet.status.in_(LIVE_STATUSES),
            )
            .limit(1)
        )
        if other is not None:
            flags.append(
                {
                    "code": "duplicate_week",
                    "message": (
                        f"Another timesheet exists for this employee and the week of "
                        f"{timesheet.week_start}. Keep one, reject the other."
                    ),
                    "other_timesheet_id": str(other),
                }
            )

    timesheet.flags = flags


def blocking_flags(timesheet: Timesheet) -> list[dict[str, Any]]:
    return [f for f in (timesheet.flags or []) if f.get("code") not in NON_BLOCKING_FLAGS]


def can_auto_approve(timesheet: Timesheet) -> bool:
    """Pure: matched, confident, has hours, nothing suspicious."""
    if not settings.auto_approve_enabled:
        return False
    confidence = timesheet.confidence or Decimal("0")
    return (
        timesheet.employee_id is not None
        and confidence >= Decimal(str(settings.auto_approve_min_confidence))
        and bool(timesheet.entries)
        and not blocking_flags(timesheet)
    )
