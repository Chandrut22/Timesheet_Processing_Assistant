import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from src.api.rest.dependencies import CurrentPrincipal, Reviewer, SessionDep
from src.core.exceptions import NotFoundError
from src.core.services.review_service import ReviewService
from src.core.services.version_history import summary, take_snapshot
from src.data.models import TimesheetVersion
from src.data.repositories.timesheet_repository import TimesheetRepository
from src.schemas.common import Page
from src.schemas.review import (
    ApproveRequest,
    BulkApproveRequest,
    BulkRejectRequest,
    BulkResult,
    EntriesUpdate,
    MatchRequest,
    RejectRequest,
    WeekUpdate,
)
from src.schemas.timesheet import (
    RestoreRequest,
    TimesheetRead,
    TimesheetVersionRead,
    TimesheetVersionSummary,
)
from src.schemas.timesheet_filters import TimesheetListQuery

router = APIRouter(prefix="/timesheets", tags=["timesheets"])


@router.get("")
async def list_timesheets(
    session: SessionDep,
    _: CurrentPrincipal,
    query: Annotated[TimesheetListQuery, Query()],
) -> Page[TimesheetRead]:
    """The review list. Filters combine with AND; repeat status / state / severity for
    several values.

    Example: ?status=needs_review&severity=high&sort=confidence&order=asc"""
    items, total = await TimesheetRepository(session).search(
        query, page=query.page, size=query.size
    )
    return Page[TimesheetRead](
        items=[TimesheetRead.model_validate(t) for t in items],
        total=total,
        page=query.page,
        size=query.size,
    )


# Bulk routes are declared before "/{timesheet_id}/..." so "bulk" is never read as an
# id.
@router.post("/bulk/approve")
async def bulk_approve(
    body: BulkApproveRequest, session: SessionDep, actor: Reviewer
) -> BulkResult:
    """Approve up to 100 timesheets. Each one gets the same checks as a single approve;
    the ones that fail are listed with the reason and the rest still go through.
    Timesheets with high-severity flags are skipped unless
    include_high_severity=true."""
    return await ReviewService(session).bulk_approve(
        body.timesheet_ids,
        body.notes,
        actor,
        include_high_severity=body.include_high_severity,
    )


@router.post("/bulk/reject")
async def bulk_reject(
    body: BulkRejectRequest, session: SessionDep, actor: Reviewer
) -> BulkResult:
    """Reject up to 100 timesheets with one reason."""
    return await ReviewService(session).bulk_reject(
        body.timesheet_ids, body.reason, actor
    )


@router.get("/{timesheet_id}")
async def get_timesheet(
    timesheet_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> TimesheetRead:
    timesheet = await TimesheetRepository(session).get(timesheet_id)
    if timesheet is None:
        raise NotFoundError("Timesheet not found.")
    return TimesheetRead.model_validate(timesheet)


@router.patch("/{timesheet_id}/entries")
async def update_entries(
    timesheet_id: uuid.UUID, body: EntriesUpdate, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).update_entries(timesheet_id, body, actor)
    return TimesheetRead.model_validate(timesheet)


@router.patch("/{timesheet_id}/week")
async def set_week(
    timesheet_id: uuid.UUID, body: WeekUpdate, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    """Move a weekly-total timesheet (no days) to another week. Saved in the current
    version unless new_version is true."""
    timesheet = await ReviewService(session).set_week(
        timesheet_id, body.week_start, actor, new_version=body.new_version
    )
    return TimesheetRead.model_validate(timesheet)


@router.post("/{timesheet_id}/match")
async def match_employee(
    timesheet_id: uuid.UUID, body: MatchRequest, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).match_employee(
        timesheet_id, body.employee_id, actor
    )
    return TimesheetRead.model_validate(timesheet)


@router.post("/{timesheet_id}/recalculate")
async def recalculate(
    timesheet_id: uuid.UUID, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    """Recalculate hours and pay with the company's current rules and rates."""
    timesheet = await ReviewService(session).recalculate(timesheet_id, actor)
    return TimesheetRead.model_validate(timesheet)


@router.post("/{timesheet_id}/approve")
async def approve(
    timesheet_id: uuid.UUID, body: ApproveRequest, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).approve(timesheet_id, body.notes, actor)
    return TimesheetRead.model_validate(timesheet)


@router.post("/{timesheet_id}/reject")
async def reject(
    timesheet_id: uuid.UUID, body: RejectRequest, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).reject(timesheet_id, body.reason, actor)
    return TimesheetRead.model_validate(timesheet)


# --- version history ----------------------------------------------------------------


def _version_fields(
    number: int,
    snap: dict[str, Any],
    saved: TimesheetVersion | None,
    current: bool = False,
) -> dict[str, Any]:
    return {
        **summary(snap),
        "version": number,
        "current": current,
        "change": saved.change if saved else None,
        "changed_by_name": saved.changed_by_name if saved else None,
        "changed_at": saved.created_at if saved else None,
        "reason": saved.reason if saved else None,
        "reprocess_run_id": saved.reprocess_run_id if saved else None,
    }


def _full(
    number: int,
    snap: dict[str, Any],
    saved: TimesheetVersion | None,
    current: bool = False,
) -> TimesheetVersionRead:
    return TimesheetVersionRead.model_validate(
        {
            # the snapshot's days and pay; the list fields (flags as codes, ...) win
            **{k: snap.get(k) for k in TimesheetVersionRead.model_fields if k in snap},
            **_version_fields(number, snap, saved, current),
        }
    )


@router.get("/{timesheet_id}/versions")
async def list_versions(
    timesheet_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> list[TimesheetVersionSummary]:
    """Every version, highest number first, with what made the next one, who and when.
    The one marked current is the timesheet as it is now (after a restore it can be an
    earlier number). Approve / reject are in the audit history, not here."""
    timesheet, saved = await ReviewService(session).versions(timesheet_id)
    by_number = {v.version: v for v in saved}
    numbers = sorted({timesheet.version, *by_number}, reverse=True)
    items = [
        _version_fields(n, take_snapshot(timesheet), by_number.get(n), current=True)
        if n == timesheet.version
        else _version_fields(n, by_number[n].snapshot, by_number[n])
        for n in numbers
    ]
    return [TimesheetVersionSummary.model_validate(i) for i in items]


@router.get("/{timesheet_id}/versions/{version}")
async def get_version(
    timesheet_id: uuid.UUID,
    version: Annotated[int, Path(ge=1)],
    session: SessionDep,
    _: CurrentPrincipal,
) -> TimesheetVersionRead:
    """One version in full: its days, hours and pay as they were."""
    timesheet, saved_versions = await ReviewService(session).versions(timesheet_id)
    saved = next((v for v in saved_versions if v.version == version), None)
    if version == timesheet.version:
        return _full(version, take_snapshot(timesheet), saved, current=True)
    if saved is None:
        raise NotFoundError(f"Version {version} of this timesheet was not found.")
    return _full(version, saved.snapshot, saved)


@router.post("/{timesheet_id}/versions/{version}/restore")
async def restore_version(
    timesheet_id: uuid.UUID,
    version: Annotated[int, Path(ge=1)],
    body: RestoreRequest,
    session: SessionDep,
    actor: Reviewer,
) -> TimesheetRead:
    """Go back to a version (admins and reviewers): the timesheet becomes that version
    again, number included; no new version is made, and what it had is kept under its
    own number. It goes back to review; not possible once exported to payroll."""
    timesheet = await ReviewService(session).restore_version(
        timesheet_id, version, body.reason, actor
    )
    return TimesheetRead.model_validate(timesheet)
