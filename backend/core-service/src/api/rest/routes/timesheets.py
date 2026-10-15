import uuid

from fastapi import APIRouter

from src.api.rest.dependencies import CurrentPrincipal, PaginationDep, Reviewer, SessionDep
from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import NotFoundError
from src.core.services.review_service import ReviewService
from src.data.repositories.timesheet_repository import TimesheetRepository
from src.schemas.common import Page
from src.schemas.review import ApproveRequest, EntriesUpdate, MatchRequest, RejectRequest
from src.schemas.timesheet import TimesheetRead

router = APIRouter(prefix="/timesheets", tags=["timesheets"])


@router.get("")
async def list_timesheets(
    session: SessionDep,
    _: CurrentPrincipal,
    paging: PaginationDep,
    status: TimesheetStatus | None = None,
    submission_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
) -> Page[TimesheetRead]:
    items, total = await TimesheetRepository(session).search(
        status=status,
        submission_id=submission_id,
        company_id=company_id,
        employee_id=employee_id,
        page=paging.page,
        size=paging.size,
    )
    return Page[TimesheetRead](
        items=[TimesheetRead.model_validate(t) for t in items],
        total=total,
        page=paging.page,
        size=paging.size,
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


@router.post("/{timesheet_id}/match")
async def match_employee(
    timesheet_id: uuid.UUID, body: MatchRequest, session: SessionDep, actor: Reviewer
) -> TimesheetRead:
    timesheet = await ReviewService(session).match_employee(timesheet_id, body.employee_id, actor)
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
