import uuid

from fastapi import APIRouter

from src.api.rest.dependencies import CurrentPrincipal, PaginationDep, SessionDep
from src.constants.timesheet_status import SubmissionSource, SubmissionStatus
from src.core.exceptions import NotFoundError
from src.data.repositories.submission_repository import SubmissionRepository
from src.schemas.common import Page
from src.schemas.submission import SubmissionRead

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("")
async def list_submissions(
    session: SessionDep,
    _: CurrentPrincipal,
    paging: PaginationDep,
    status: SubmissionStatus | None = None,
    source: SubmissionSource | None = None,
    company_id: uuid.UUID | None = None,
) -> Page[SubmissionRead]:
    items, total = await SubmissionRepository(session).search(
        status=status, source=source, company_id=company_id, page=paging.page, size=paging.size
    )
    return Page[SubmissionRead](
        items=[SubmissionRead.model_validate(s) for s in items],
        total=total,
        page=paging.page,
        size=paging.size,
    )


@router.get("/{submission_id}")
async def get_submission(
    submission_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> SubmissionRead:
    submission = await SubmissionRepository(session).get(submission_id)
    if submission is None:
        raise NotFoundError("Submission not found.")
    return SubmissionRead.model_validate(submission)
