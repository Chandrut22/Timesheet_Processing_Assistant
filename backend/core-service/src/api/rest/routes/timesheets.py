import uuid

from fastapi import APIRouter

from src.api.rest.dependencies import CurrentPrincipal, PaginationDep, SessionDep
from src.constants.timesheet_status import TimesheetStatus
from src.core.exceptions import NotFoundError
from src.data.repositories.timesheet_repository import TimesheetRepository
from src.schemas.common import Page
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
