"""The submission's final state, from its timesheets and documents."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import (
    DocumentStatus,
    SubmissionState,
    SubmissionStatus,
    TimesheetStatus,
)
from src.core.services.activity_log import set_state, state_from_timesheets
from src.data.models import Submission, Timesheet


async def has_timesheets(session: AsyncSession, document_id: uuid.UUID) -> bool:
    """Live (not superseded) timesheets from this document: a reprocess leaves those."""
    found = await session.scalar(
        select(Timesheet.id)
        .where(
            Timesheet.document_id == document_id,
            Timesheet.status != TimesheetStatus.SUPERSEDED,
        )
        .limit(1)
    )
    return found is not None


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
    if failed:
        set_state(session, submission, SubmissionState.FAILED, reason=failed[0].error)
    else:
        set_state(
            session,
            submission,
            SubmissionState.IGNORED,
            reason="No timesheet found in this email or upload.",
        )
