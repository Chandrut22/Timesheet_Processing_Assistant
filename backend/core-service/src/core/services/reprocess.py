"""Reprocessing, shared by the API (start a run) and the worker (do it, finish it).

A run records who asked, when and why, and a summary of the timesheets BEFORE and
AFTER. A reprocess updates the existing timesheets IN PLACE: the same timesheet (same
id) gets the new data and its version goes up by one; what it was before is kept in
timesheet_versions (change "reprocessed"), so it can be compared or rolled back.

Which old timesheet does a newly extracted one update? (pick_predecessor) Same
document, then the same name and week, the same code and week, the same name, the
same code; else, when the document had exactly one timesheet and gives exactly one
again, that one. A new person / week becomes a new timesheet (version 1). An old
timesheet that was not found again is rejected with the removed_by_reprocess flag:
nothing is deleted, and a reviewer can still approve it."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import ReprocessStatus, TimesheetChange, TimesheetStatus
from src.core.services.audit import record_event
from src.core.services.version_history import save_version, take_snapshot
from src.data.models import ReprocessRun, Submission, Timesheet

MAX_ERROR_CHARS = 2000
REMOVED_FLAG = "removed_by_reprocess"

# Copied from the newly extracted timesheet onto the one it updates. Matching, pay
# and the decision are worked out again afterwards by the pipeline.
ADOPTED_FIELDS = (
    "company_id",
    "employee_id",
    "extracted_name",
    "extracted_code",
    "extracted_company_name",
    "week_start",
    "regular_hours",
    "overtime_hours",
    "double_time_hours",
    "holiday_hours",
    "stated_total",
    "email_stated_total",
    "read_confidence",
    "confidence",
    "currency",
    "hourly_rate",
    "overtime_rate",
    "double_time_rate",
    "holiday_rate",
    "regular_amount",
    "overtime_amount",
    "double_time_amount",
    "holiday_amount",
    "match_method",
    "match_reason",
    "flags",
    "entries",
)


def _money(*parts: Decimal | None) -> float | None:
    if any(p is None for p in parts):
        return None
    return float(sum((p for p in parts if p is not None), Decimal("0")))


def summarize(timesheet: Timesheet) -> dict[str, Any]:
    """What a reviewer wants to compare before / after (plain JSON)."""
    hours = (
        timesheet.regular_hours,
        timesheet.overtime_hours,
        timesheet.double_time_hours,
        timesheet.holiday_hours,
    )
    return {
        "id": str(timesheet.id),
        "version": timesheet.version,
        "document_id": str(timesheet.document_id) if timesheet.document_id else None,
        "name": timesheet.extracted_name,
        "code": timesheet.extracted_code,
        "employee_id": str(timesheet.employee_id) if timesheet.employee_id else None,
        "match_method": timesheet.match_method,
        "confidence": float(timesheet.confidence) if timesheet.confidence is not None else None,
        "status": timesheet.status,
        "week_start": timesheet.week_start.isoformat() if timesheet.week_start else None,
        "total_hours": float(sum((h or Decimal("0") for h in hours), Decimal("0"))),
        "gross_amount": _money(
            timesheet.regular_amount,
            timesheet.overtime_amount,
            timesheet.double_time_amount,
            timesheet.holiday_amount,
        ),
        "severity": timesheet.severity,
        "flags": [f.get("code") for f in timesheet.flags or []],
        # So an approval cleared by the reprocess can be given back if the run fails.
        "reviewed_by_id": str(timesheet.reviewed_by_id) if timesheet.reviewed_by_id else None,
        "reviewed_by_name": timesheet.reviewed_by_name,
        "reviewed_at": timesheet.reviewed_at.isoformat() if timesheet.reviewed_at else None,
    }


def snapshot(state: str, timesheets: Sequence[Timesheet]) -> dict[str, Any]:
    items = [summarize(t) for t in timesheets]
    return {
        "state": state,
        "timesheets": items,
        "count": len(items),
        "unmatched": sum(1 for t in items if t["employee_id"] is None),
        "needs_review": sum(1 for t in items if t["status"] == TimesheetStatus.NEEDS_REVIEW),
        "approved": sum(1 for t in items if t["status"] == TimesheetStatus.APPROVED),
    }


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def pick_predecessor(
    new: Timesheet, olds: Sequence[Timesheet], *, only_one_new: bool
) -> Timesheet | None:
    """Pure: which old timesheet of the same document does this new one update?"""
    same_doc = [o for o in olds if o.document_id == new.document_id]
    name, code = _norm(new.extracted_name), _norm(new.extracted_code)
    tests = (
        (bool(name), lambda o: _norm(o.extracted_name) == name and o.week_start == new.week_start),
        (bool(code), lambda o: _norm(o.extracted_code) == code and o.week_start == new.week_start),
        (bool(name), lambda o: _norm(o.extracted_name) == name),
        (bool(code), lambda o: _norm(o.extracted_code) == code),
    )
    for usable, same in tests:
        if usable:
            hits = [o for o in same_doc if same(o)]
            if len(hits) == 1:
                return hits[0]
    if only_one_new and len(same_doc) == 1:
        return same_doc[0]
    return None


async def previous_timesheets(
    session: AsyncSession, document_id: uuid.UUID, run_id: uuid.UUID
) -> list[Timesheet]:
    """The document's timesheets this reprocess has not updated yet."""
    rows = await session.scalars(
        select(Timesheet)
        .where(
            Timesheet.document_id == document_id,
            Timesheet.reprocess_run_id.is_distinct_from(run_id),
            Timesheet.status != TimesheetStatus.EXPORTED,  # payroll data never changes
        )
        .order_by(Timesheet.created_at, Timesheet.id)
    )
    return list(rows.all())


def adopt(session: AsyncSession, old: Timesheet, new: Timesheet, run: ReprocessRun) -> Timesheet:
    """Give the old timesheet the newly extracted data (same id, version + 1) and keep
    what it was in timesheet_versions. Returns the old timesheet, which the pipeline
    then matches, prices and decides like a new one. `new` is never saved."""
    before = take_snapshot(old)
    for name in ADOPTED_FIELDS:
        setattr(old, name, getattr(new, name))
    old.status = TimesheetStatus.NEEDS_REVIEW  # the decision is made again
    old.reviewed_by_id = None
    old.reviewed_by_name = None
    old.reviewed_at = None
    old.notes = None
    old.reprocess_run_id = run.id
    save_version(
        session,
        old,
        before,
        TimesheetChange.REPROCESSED,
        actor_id=run.requested_by_id,
        actor_name=run.requested_by_name,
        reprocess_run_id=run.id,
        reason=run.reason,
        force=True,
    )
    return old


def retire(session: AsyncSession, old: Timesheet, run: ReprocessRun) -> None:
    """An old timesheet the reprocess did not find again: rejected, flagged, kept.
    A status change only (no new version); the audit log has it."""
    if old.status == TimesheetStatus.EXPORTED:
        return  # never happens (exported blocks a reprocess); never touch payroll data
    old.flags = [
        *(f for f in old.flags or [] if f.get("code") != REMOVED_FLAG),
        {
            "code": REMOVED_FLAG,
            "message": "Not found when the document was read again (reprocess: "
            f"{run.reason}). Kept for the record; approve it if it is still right.",
        },
    ]
    old.status = TimesheetStatus.REJECTED
    old.reviewed_by_id = run.requested_by_id
    old.reviewed_by_name = run.requested_by_name
    old.reviewed_at = datetime.now(UTC)
    old.notes = "Removed by a reprocess: not found when the document was read again."
    old.reprocess_run_id = run.id
    record_event(
        session,
        entity_type="timesheet",
        entity_id=old.id,
        action="removed_by_reprocess",
        details={"reprocess_run_id": str(run.id), "reason": run.reason},
    )


def _removed(timesheet: Timesheet) -> bool:
    return any(f.get("code") == REMOVED_FLAG for f in timesheet.flags or [])


async def finish_run(session: AsyncSession, run_id: uuid.UUID, *, error: str | None = None) -> None:
    """Worker side: store the AFTER summary and close the run. Does not commit (the
    caller commits with the rest of the work)."""
    run = await session.get(ReprocessRun, run_id, populate_existing=True)
    if run is None or run.status != ReprocessStatus.RUNNING:
        return
    submission = await session.get(Submission, run.submission_id)
    touched = (
        await session.scalars(
            select(Timesheet)
            .where(Timesheet.reprocess_run_id == run_id)
            .order_by(Timesheet.created_at, Timesheet.id)
        )
    ).all()
    produced = [t for t in touched if not _removed(t)]
    after = snapshot(submission.state if submission else "", produced)

    # Old timesheet -> what it is now: itself (updated in place) or None (removed).
    kept = {str(t.id) for t in produced}
    after["replaced"] = {
        item["id"]: (item["id"] if item["id"] in kept else None)
        for item in run.before_result.get("timesheets", [])
    }
    after["removed"] = [str(t.id) for t in touched if _removed(t)]

    run.after_result = after
    run.status = ReprocessStatus.FAILED if error else ReprocessStatus.COMPLETED
    run.error = error[:MAX_ERROR_CHARS] if error else None
    run.completed_at = datetime.now(UTC)
