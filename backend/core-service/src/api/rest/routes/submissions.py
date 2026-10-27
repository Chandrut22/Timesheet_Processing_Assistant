import uuid

from fastapi import APIRouter
from fastapi import status as http_status

from src.api.rest.dependencies import CurrentPrincipal, PaginationDep, Reviewer, SessionDep
from src.constants.timesheet_status import SubmissionSource, SubmissionState, SubmissionStatus
from src.core.exceptions import NotFoundError
from src.core.services.submission_service import SubmissionService
from src.data.repositories.activity_repository import ActivityRepository
from src.data.repositories.submission_repository import SubmissionRepository
from src.schemas.common import Page
from src.schemas.review import AuditEventRead
from src.schemas.submission import (
    ProcessingStepRead,
    ReprocessRequest,
    ReprocessRunRead,
    StateChangeRead,
    SubmissionRead,
    SubmissionTimeline,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("")
async def list_submissions(
    session: SessionDep,
    _: CurrentPrincipal,
    paging: PaginationDep,
    status: SubmissionStatus | None = None,
    state: SubmissionState | None = None,
    source: SubmissionSource | None = None,
    company_id: uuid.UUID | None = None,
) -> Page[SubmissionRead]:
    items, total = await SubmissionRepository(session).search(
        status=status,
        state=state,
        source=source,
        company_id=company_id,
        page=paging.page,
        size=paging.size,
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


@router.get("/{submission_id}/timeline")
async def get_timeline(
    submission_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> SubmissionTimeline:
    """The email state log, the step-by-step log and every decision, oldest first."""
    submission = await SubmissionRepository(session).get(submission_id)
    if submission is None:
        raise NotFoundError("Submission not found.")
    activity = ActivityRepository(session)
    return SubmissionTimeline(
        submission=SubmissionRead.model_validate(submission),
        states=[StateChangeRead.model_validate(s) for s in await activity.states(submission_id)],
        steps=[ProcessingStepRead.model_validate(s) for s in await activity.steps(submission_id)],
        audit=[AuditEventRead.model_validate(e) for e in await activity.audit(submission_id)],
        reprocess_runs=[
            ReprocessRunRead.model_validate(r) for r in await activity.reprocess_runs(submission_id)
        ],
    )


@router.post("/{submission_id}/reprocess", status_code=http_status.HTTP_202_ACCEPTED)
async def reprocess(
    submission_id: uuid.UUID, body: ReprocessRequest, session: SessionDep, actor: Reviewer
) -> ReprocessRunRead:
    """Run the email (or one attachment) again with the current master data. A reason is
    required. The timesheets are updated in place (version + 1); their earlier data is
    kept in the version history, so nothing is lost."""
    run = await SubmissionService(session).reprocess(
        submission_id,
        body.reason,
        actor,
        document_id=body.document_id,
        refetch=body.refetch,
        confirm_approved=body.confirm_approved,
    )
    return ReprocessRunRead.model_validate(run)


@router.get("/{submission_id}/reprocess-runs")
async def reprocess_runs(
    submission_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> list[ReprocessRunRead]:
    """Reprocessing history: who, when, why, and the results before and after."""
    runs = await SubmissionService(session).runs(submission_id)
    return [ReprocessRunRead.model_validate(r) for r in runs]
