"""Claiming a submission for one run of the worker."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import SubmissionStatus
from src.data.models import Submission

CLAIMABLE = (SubmissionStatus.RECEIVED, SubmissionStatus.FAILED)


def claimable(now: datetime) -> ColumnElement[bool]:
    """Waiting or failed, or "processing" with no progress for worker_stale_after_seconds
    (its worker died). A job that is really running is never taken over: a second copy
    of the same job (queued twice, or handed out again by Redis) finds nothing to do."""
    stale = now - timedelta(seconds=settings.worker_stale_after_seconds)
    return or_(
        Submission.status.in_(CLAIMABLE),
        and_(Submission.status == SubmissionStatus.PROCESSING, Submission.updated_at < stale),
    )


async def claim(
    session: AsyncSession, submission_id: uuid.UUID, retry_token: uuid.UUID | None
) -> int | None:
    """Take the submission for this run; returns the run number (1, 2, ...) or None.
    A scheduled retry only claims it while its token is still the current one, so a
    retry made stale by a reprocess does nothing."""
    query = update(Submission).where(Submission.id == submission_id, claimable(datetime.now(UTC)))
    if retry_token is not None:
        query = query.where(Submission.retry_token == retry_token)
    attempt = await session.scalar(
        query.values(
            status=SubmissionStatus.PROCESSING,
            error=None,
            attempts=Submission.attempts + 1,
            retry_at=None,
            retry_token=None,
            updated_at=datetime.now(UTC),  # the claim is progress (see claimable)
        ).returning(Submission.attempts)
    )
    await session.commit()
    return attempt
