"""Checks that need the database (duplicates), and the auto-approve decision."""

import hashlib
import uuid
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import DocumentStatus, TimesheetStatus
from src.data.models import Document, Timesheet

# Flags this module owns: removed and recomputed on every validation.
VALIDATION_FLAG_CODES = frozenset({"duplicate_file", "duplicate_week"})

# Flags that are only information and do not stop auto-approval.
# handwriting_present: a photo / scan with some handwriting, but the hours are printed.
NON_BLOCKING_FLAGS = frozenset({"holiday_worked", "company_from_sheet", "handwriting_present"})

LIVE_STATUSES = (TimesheetStatus.NEEDS_REVIEW, TimesheetStatus.APPROVED, TimesheetStatus.EXPORTED)


def _week_lock_key(employee_id: uuid.UUID, week_start: date) -> int:
    """A stable signed 64-bit number for (employee, week): the advisory lock's key."""
    digest = hashlib.blake2b(f"{employee_id}:{week_start}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


async def lock_employee_weeks(
    session: AsyncSession, pairs: Iterable[tuple[uuid.UUID | None, date | None]]
) -> None:
    """Take a PostgreSQL advisory lock per (employee, week), held until the transaction
    ends. Two workers (or reviewers) checking the same person and week then run one
    after the other, so the second always sees the first one's committed timesheet.
    Keys are taken in sorted order so two sessions can never deadlock on them.
    Locks are re-entrant within a session, so taking one twice is harmless."""
    keys = sorted(
        {_week_lock_key(emp, week) for emp, week in pairs if emp is not None and week is not None}
    )
    for key in keys:
        await session.execute(select(func.pg_advisory_xact_lock(key)))


async def other_paid_timesheet(session: AsyncSession, timesheet: Timesheet) -> Timesheet | None:
    """Another approved or exported timesheet for the same employee and week, if any."""
    if timesheet.employee_id is None or timesheet.week_start is None:
        return None
    other: Timesheet | None = await session.scalar(
        select(Timesheet)
        .where(
            Timesheet.employee_id == timesheet.employee_id,
            Timesheet.week_start == timesheet.week_start,
            Timesheet.id != timesheet.id,
            Timesheet.status.in_((TimesheetStatus.APPROVED, TimesheetStatus.EXPORTED)),
        )
        .limit(1)
    )
    return other


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
        await lock_employee_weeks(session, [(timesheet.employee_id, timesheet.week_start)])
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


def _ranges(days: Sequence[date]) -> str:
    """[1, 2, 3, 5] Oct -> '2026-10-01 to 2026-10-03, 2026-10-05'"""
    parts: list[str] = []
    start = prev = None
    for day in sorted(days):
        if start is None:
            start = prev = day
        elif prev is not None and (day - prev).days == 1:
            prev = day
        else:
            parts.append(f"{start}" if start == prev else f"{start} to {prev}")
            start = prev = day
    if start is not None:
        parts.append(f"{start}" if start == prev else f"{start} to {prev}")
    return ", ".join(parts)


def check_assignment(timesheet: Timesheet, start: date | None, end: date | None) -> None:
    """Flag hours worked outside the employee's assignment dates (rebuilt every time)."""
    flags = [f for f in (timesheet.flags or []) if f.get("code") != "outside_assignment"]
    outside = [
        e.work_date
        for e in timesheet.entries
        if e.hours > 0
        and ((start is not None and e.work_date < start) or (end is not None and e.work_date > end))
    ]
    if outside:
        period = f"{start or 'open'} to {end or 'open'}"
        flags.append(
            {
                "code": "outside_assignment",
                "message": f"Hours on {_ranges(outside)} fall outside the assignment ({period}).",
                "dates": [d.isoformat() for d in sorted(outside)],
            }
        )
    timesheet.flags = flags
