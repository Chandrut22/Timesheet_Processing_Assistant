"""The submission's final state, from its timesheets and documents."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import (
    SKIPPED_BY_CLASSIFIER,
    DocumentStatus,
    SubmissionState,
    SubmissionStatus,
)
from src.core.services.activity_log import set_state, state_from_timesheets
from src.data.models import Submission, Timesheet


async def already_extracted(
    session: AsyncSession, document_id: uuid.UUID, reprocess_run_id: uuid.UUID | None
) -> bool:
    """Skip this document? A normal run: it already has timesheets (a retry after a
    crash halfway). A reprocess: this run already updated its timesheets."""
    query = select(Timesheet.id).where(Timesheet.document_id == document_id)
    if reprocess_run_id is not None:
        query = query.where(Timesheet.reprocess_run_id == reprocess_run_id)
    return await session.scalar(query.limit(1)) is not None


async def finish(session: AsyncSession, submission: Submission) -> None:
    submission.status = SubmissionStatus.PROCESSED
    submission.processed_at = datetime.now(UTC)
    statuses = (
        await session.scalars(
            select(Timesheet.status).where(Timesheet.submission_id == submission.id)
        )
    ).all()
    state = state_from_timesheets(statuses)
    if state is not None:
        set_state(session, submission, state)
        return
    failed = [d for d in submission.documents if d.status == DocumentStatus.FAILED]
    skipped = [
        d
        for d in submission.documents
        if (d.error or "").startswith(SKIPPED_BY_CLASSIFIER)
    ]
    if failed:
        set_state(session, submission, SubmissionState.FAILED, reason=failed[0].error)
    elif skipped:
        # Say why: the classifier skipped it (it may be wrong), not "no timesheet
        # found".
        set_state(session, submission, SubmissionState.IGNORED, reason=skipped[0].error)
    else:
        set_state(
            session,
            submission,
            SubmissionState.IGNORED,
            reason="No timesheet found in this email or upload.",
        )
