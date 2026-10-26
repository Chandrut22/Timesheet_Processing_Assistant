"""Timesheet versions: save what a timesheet was before a data change, and restore it.

A NEW version is made by a reprocess or a reviewer's "Create as new version". A plain
Save (days, week, employee, recalculation) changes the current version in place.
Restoring a version makes no new version: the timesheet goes back to that version
(its number included) and the data it had is kept under its own number.

    before = take_snapshot(timesheet)
    ... change the days / employee / week / pay ...
    await save_version(session, timesheet, before, TimesheetChange.ENTRIES_EDITED, actor=actor)

save_version keeps `before` under the current number N in timesheet_versions and gives
the timesheet the next free number (the highest so far + 1: after going back to an
earlier version, N + 1 may already exist). switch_to_version restores one. Approve /
reject are status changes: they are in the audit log, not here."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import TimesheetChange
from src.core.rbac.principal import Principal
from src.data.models import Timesheet, TimesheetVersion
from src.data.models.postgres.timesheet_entry import TimesheetEntry

CENT = Decimal("0.01")

# The timesheet's data, as kept in a version. Not kept: ids that never change
# (submission, document), the export link, and generated columns (total, gross).
UUID_FIELDS = ("company_id", "employee_id", "reviewed_by_id")
DATE_FIELDS = ("week_start",)
DATETIME_FIELDS = ("reviewed_at",)
DECIMAL_FIELDS = (
    "regular_hours",
    "overtime_hours",
    "double_time_hours",
    "holiday_hours",
    "stated_total",
    "email_stated_total",
    "read_confidence",
    "confidence",
    "hourly_rate",
    "overtime_rate",
    "double_time_rate",
    "holiday_rate",
    "regular_amount",
    "overtime_amount",
    "double_time_amount",
    "holiday_amount",
)
TEXT_FIELDS = (
    "extracted_name",
    "extracted_code",
    "extracted_company_name",
    "status",
    "currency",
    "match_method",
    "match_reason",
    "notes",
    "reviewed_by_name",
)
SNAPSHOT_FIELDS = (
    *UUID_FIELDS,
    *DATE_FIELDS,
    *DATETIME_FIELDS,
    *DECIMAL_FIELDS,
    *TEXT_FIELDS,
    "flags",
    "entries",
)
# The review decision, not the data: a change of only these makes no version.
DECISION_FIELDS = frozenset(
    {"status", "reviewed_by_id", "reviewed_by_name", "reviewed_at", "notes"}
)


def take_snapshot(timesheet: Timesheet) -> dict[str, Any]:
    """The timesheet's data as plain JSON (decimals as strings, so nothing is rounded)."""
    snap: dict[str, Any] = {}
    for name in UUID_FIELDS:
        value = getattr(timesheet, name)
        snap[name] = str(value) if value is not None else None
    for name in (*DATE_FIELDS, *DATETIME_FIELDS):
        value = getattr(timesheet, name)
        snap[name] = value.isoformat() if value is not None else None
    for name in DECIMAL_FIELDS:  # all NUMERIC(_, 2): 40 and 40.00 are the same value
        value = getattr(timesheet, name)
        snap[name] = str(Decimal(value).quantize(CENT)) if value is not None else None
    for name in TEXT_FIELDS:
        snap[name] = getattr(timesheet, name)
    snap["flags"] = [dict(f) for f in timesheet.flags or []]
    snap["entries"] = [e.to_json() for e in timesheet.entries or []]
    return snap


def restore_snapshot(timesheet: Timesheet, snap: dict[str, Any]) -> None:
    """Put a snapshot's data back on the timesheet (status and review fields included;
    the caller decides the status after a rollback)."""
    for name in UUID_FIELDS:
        value = snap.get(name)
        setattr(timesheet, name, uuid.UUID(value) if value else None)
    for name in DATE_FIELDS:
        value = snap.get(name)
        setattr(timesheet, name, date.fromisoformat(value) if value else None)
    for name in DATETIME_FIELDS:
        value = snap.get(name)
        setattr(timesheet, name, datetime.fromisoformat(value) if value else None)
    for name in DECIMAL_FIELDS:
        value = snap.get(name)
        setattr(timesheet, name, Decimal(value) if value is not None else None)
    for name in TEXT_FIELDS:
        setattr(timesheet, name, snap.get(name))
    timesheet.flags = [dict(f) for f in snap.get("flags") or []]
    timesheet.entries = [TimesheetEntry.from_json(e) for e in snap.get("entries") or []]


def data_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """True when anything other than the review decision differs."""
    return any(
        before.get(name) != after.get(name)
        for name in SNAPSHOT_FIELDS
        if name not in DECISION_FIELDS
    )


async def keep(
    session: AsyncSession,
    timesheet: Timesheet,
    snap: dict[str, Any],
    change: TimesheetChange,
    *,
    actor: Principal | None = None,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
    reprocess_run_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> TimesheetVersion:
    """Store `snap` as the timesheet's current version number. A row for that number
    already exists when the timesheet went back to it: its data is brought up to date
    (Save edits it in place) and its first `change` / who / when are kept."""
    stored = await session.scalar(
        select(TimesheetVersion).where(
            TimesheetVersion.timesheet_id == timesheet.id,
            TimesheetVersion.version == timesheet.version,
        )
    )
    if stored is not None:
        stored.snapshot = snap
        return stored
    stored = TimesheetVersion(
        timesheet_id=timesheet.id,
        version=timesheet.version,
        change=change,
        changed_by_id=actor.id if actor else actor_id,
        changed_by_name=actor.name if actor else actor_name,
        reprocess_run_id=reprocess_run_id,
        reason=reason,
        snapshot=snap,
    )
    session.add(stored)
    return stored


async def next_number(session: AsyncSession, timesheet: Timesheet) -> int:
    """The highest version number used so far + 1."""
    highest = await session.scalar(
        select(func.max(TimesheetVersion.version)).where(
            TimesheetVersion.timesheet_id == timesheet.id
        )
    )
    return max(highest or 0, timesheet.version) + 1


async def save_version(
    session: AsyncSession,
    timesheet: Timesheet,
    before: dict[str, Any],
    change: TimesheetChange,
    *,
    actor: Principal | None = None,
    actor_id: uuid.UUID | None = None,
    actor_name: str | None = None,
    reprocess_run_id: uuid.UUID | None = None,
    reason: str | None = None,
    force: bool = False,
) -> TimesheetVersion | None:
    """Keep `before` as the current version and give the timesheet the next number.
    Nothing is saved when the data did not change, unless force=True (a reprocess or
    "Create as new version" always counts). Returns the kept version, or None. Does not
    commit."""
    if not force and not data_changed(before, take_snapshot(timesheet)):
        return None
    stored = await keep(
        session,
        timesheet,
        before,
        change,
        actor=actor,
        actor_id=actor_id,
        actor_name=actor_name,
        reprocess_run_id=reprocess_run_id,
        reason=reason,
    )
    timesheet.version = await next_number(session, timesheet)
    return stored


async def switch_to_version(
    session: AsyncSession,
    timesheet: Timesheet,
    target: TimesheetVersion,
    *,
    actor: Principal,
    reason: str | None,
) -> None:
    """Go back to `target`: the data the timesheet has now is kept under its current
    number, then it gets `target`'s data and number. No new version is made, so going
    back and forth is always possible. Status and review fields come from `target`
    (the caller decides the status). Does not commit."""
    await keep(
        session,
        timesheet,
        take_snapshot(timesheet),
        TimesheetChange.ROLLED_BACK,
        actor=actor,
        reason=reason,
    )
    restore_snapshot(timesheet, target.snapshot)
    timesheet.version = target.version


def summary(snap: dict[str, Any]) -> dict[str, Any]:
    """What a version list shows: days, hours, gross, employee, week, status."""

    def number(name: str) -> Decimal | None:
        value = snap.get(name)
        return Decimal(value) if value is not None else None

    hours = [number(n) or Decimal("0") for n in DECIMAL_FIELDS[:4]]
    amounts = [number(n) for n in ("regular_amount", "overtime_amount", "double_time_amount")]
    amounts.append(number("holiday_amount"))
    gross = None if any(a is None for a in amounts) else sum(a for a in amounts if a is not None)
    return {
        "employee_id": snap.get("employee_id"),
        "extracted_name": snap.get("extracted_name"),
        "week_start": snap.get("week_start"),
        "status": snap.get("status"),
        "days": len(snap.get("entries") or []),
        "total_hours": sum(hours, Decimal("0")),
        "gross_amount": gross,
        "flags": [f.get("code") for f in snap.get("flags") or []],
    }
