import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.api.rest.dependencies import CurrentPrincipal, Reviewer, SessionDep
from src.core.exceptions import NotFoundError
from src.core.services.review_service import ReviewService
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
)
from src.schemas.timesheet import TimesheetRead
from src.schemas.timesheet_filters import TimesheetListQuery

router = APIRouter(prefix="/timesheets", tags=["timesheets"])


@router.get("")
async def list_timesheets(
    session: SessionDep,
    _: CurrentPrincipal,
    query: Annotated[TimesheetListQuery, Query()],
) -> Page[TimesheetRead]:
    """The review list. Filters combine with AND; repeat status / state / severity for
    several values. Replaced (superseded) versions are left out unless
    include_superseded=true or status=superseded.

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


# Bulk routes are declared before "/{timesheet_id}/..." so "bulk" is never read as an id.
@router.post("/bulk/approve")
async def bulk_approve(
    body: BulkApproveRequest, session: SessionDep, actor: Reviewer
) -> BulkResult:
    """Approve up to 100 timesheets. Each one gets the same checks as a single approve;
    the ones that fail are listed with the reason and the rest still go through.
    Timesheets with high-severity flags are skipped unless include_high_severity=true."""
    return await ReviewService(session).bulk_approve(
        body.timesheet_ids,
        body.notes,
        actor,
        include_high_severity=body.include_high_severity,
    )


@router.post("/bulk/reject")
async def bulk_reject(body: BulkRejectRequest, session: SessionDep, actor: Reviewer) -> BulkResult:
    """Reject up to 100 timesheets with one reason."""
    return await ReviewService(session).bulk_reject(body.timesheet_ids, body.reason, actor)


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


@router.post("/{timesheet_id}/match")
async def match_employee(
    timesheet_id: uuid.UUID, body: MatchRequest, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).match_employee(timesheet_id, body.employee_id, actor)
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
