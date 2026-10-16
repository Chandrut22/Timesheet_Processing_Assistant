"""Reprocessing history, shared by the API (start a run) and the worker (finish it).

A run records who asked, when and why, and a snapshot of the results BEFORE (the
timesheets it replaces) and AFTER (the timesheets it produced). The old timesheets
are kept with status "superseded" and linked to the version that replaced them."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import ReprocessStatus, TimesheetStatus
from src.data.models import ReprocessRun, Submission, Timesheet

MAX_ERROR_CHARS = 2000


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
        "total_hours": float(sum((h for h in hours), Decimal("0"))),
        "gross_amount": _money(
            timesheet.regular_amount,
            timesheet.overtime_amount,
            timesheet.double_time_amount,
            timesheet.holiday_amount,
        ),
        "severity": timesheet.severity,
        "flags": [f.get("code") for f in timesheet.flags or []],
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


def pick_successor(old: dict[str, Any], new: Sequence[dict[str, Any]]) -> str | None:
    """Pure: which new timesheet replaces this old one? Same document, then the same
    name, else the same code, else the only one from that document. None = no match."""
    same_doc = [n for n in new if n["document_id"] == old["document_id"]]
    for key in ("name", "code"):
        if _norm(old.get(key)):
            hits = [n for n in same_doc if _norm(n.get(key)) == _norm(old.get(key))]
            if len(hits) == 1:
                return str(hits[0]["id"])
    if len(same_doc) == 1:
        return str(same_doc[0]["id"])
    return None


async def next_version(session: AsyncSession, document_id: uuid.UUID | None) -> int:
    """1 for a first extraction; old highest version + 1 after a reprocess."""
    if document_id is None:
        return 1
    versions = (
        await session.scalars(select(Timesheet.version).where(Timesheet.document_id == document_id))
    ).all()
    return max(versions, default=0) + 1


async def finish_run(session: AsyncSession, run_id: uuid.UUID, *, error: str | None = None) -> None:
    """Worker side: link old -> new versions, store the AFTER snapshot, close the run.
    Does not commit (the caller commits with the rest of the work)."""
    run = await session.get(ReprocessRun, run_id, populate_existing=True)
    if run is None or run.status != ReprocessStatus.RUNNING:
        return
    submission = await session.get(Submission, run.submission_id)
    produced = (
        await session.scalars(
            select(Timesheet)
            .where(Timesheet.reprocess_run_id == run_id)
            .order_by(Timesheet.created_at, Timesheet.id)
        )
    ).all()
    after = snapshot(submission.state if submission else "", produced)

    # Old version -> the version that replaced it (kept even when nothing replaced it).
    new_items = after["timesheets"]
    old_ids = [uuid.UUID(t["id"]) for t in run.before_result.get("timesheets", [])]
    replaced = {}
    if old_ids:
        old_rows = (await session.scalars(select(Timesheet).where(Timesheet.id.in_(old_ids)))).all()
        for old in old_rows:
            successor = pick_successor(summarize(old), new_items)
            if successor is not None:
                old.superseded_by_id = uuid.UUID(successor)
            replaced[str(old.id)] = successor
    after["replaced"] = replaced  # old id -> new id (or None)

    run.after_result = after
    run.status = ReprocessStatus.FAILED if error else ReprocessStatus.COMPLETED
    run.error = error[:MAX_ERROR_CHARS] if error else None
    run.completed_at = datetime.now(UTC)
