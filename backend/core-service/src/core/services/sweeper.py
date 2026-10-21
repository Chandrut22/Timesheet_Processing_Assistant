"""The sweeper: finds work that was lost and puts it back in the queue. Runs every
sweeper_interval_seconds from Celery beat (in compose: inside core-worker, `worker -B`).

Work gets lost when:
  - a submission was committed but queuing it failed (Redis down for a moment):
    it stays "received" and no job exists                          -> queue it again
  - the worker died mid-job and its job is gone: the submission stays "processing"
    with no progress for worker_stale_after_seconds                 -> back to "received", queue it
  - a scheduled retry was lost (Redis restarted): retry_at passed long ago
                                                                    -> queue the retry again

Each change is one atomic UPDATE ... WHERE <still stuck> RETURNING, so two sweepers (or a
sweeper and a worker) never pick the same row. Queuing a submission twice is harmless:
the worker's claim lets only one job take it."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    ReprocessStatus,
    StepName,
    StepResult,
    SubmissionStatus,
)
from src.control.workers.dispatch import enqueue_submission
from src.core.services.activity_log import record_step
from src.data.clients import upload_buffer
from src.data.models import ReprocessRun, Submission
from src.observability.tracing.spans import pipeline_span

logger = logging.getLogger(__name__)

BATCH = 50  # per sweep; the next sweep takes the rest


@dataclass(frozen=True, slots=True)
class Requeue:
    submission_id: uuid.UUID
    reason: str
    retry_token: uuid.UUID | None = None


def is_stuck(submission: Submission, now: datetime) -> bool:
    """Pure: "received" for longer than the grace time, or "processing" with no progress
    for worker_stale_after_seconds. Such a submission may be reprocessed by hand."""
    updated = submission.updated_at
    if updated is None:
        return False
    if submission.status == SubmissionStatus.RECEIVED:
        return updated < now - timedelta(seconds=settings.sweeper_grace_seconds)
    if submission.status == SubmissionStatus.PROCESSING:
        return updated < now - timedelta(seconds=settings.worker_stale_after_seconds)
    return False


async def _running_reprocess(session: AsyncSession, submission_id: uuid.UUID) -> uuid.UUID | None:
    run_id: uuid.UUID | None = await session.scalar(
        select(ReprocessRun.id)
        .where(
            ReprocessRun.submission_id == submission_id,
            ReprocessRun.status == ReprocessStatus.RUNNING,
        )
        .limit(1)
    )
    return run_id


async def find_and_mark(session: AsyncSession, now: datetime) -> list[Requeue]:
    """Pick the lost submissions and mark them (so the next sweep does not take them
    again straight away). Does not commit."""
    grace = now - timedelta(seconds=settings.sweeper_grace_seconds)
    stale = now - timedelta(seconds=settings.worker_stale_after_seconds)
    found: list[Requeue] = []

    # 1. Committed but never queued (or the job was lost before it started).
    waiting = select(Submission.id).where(
        Submission.status == SubmissionStatus.RECEIVED, Submission.updated_at < grace
    )
    rows = await session.scalars(
        update(Submission)
        .where(Submission.id.in_(waiting.limit(BATCH).scalar_subquery()))
        .where(Submission.status == SubmissionStatus.RECEIVED, Submission.updated_at < grace)
        .values(updated_at=func.now())
        .returning(Submission.id)
    )
    found += [Requeue(i, "It was waiting in the queue too long; queued again.") for i in rows]

    # 2. The worker died mid-job.
    abandoned = select(Submission.id).where(
        Submission.status == SubmissionStatus.PROCESSING, Submission.updated_at < stale
    )
    rows = await session.scalars(
        update(Submission)
        .where(Submission.id.in_(abandoned.limit(BATCH).scalar_subquery()))
        .where(Submission.status == SubmissionStatus.PROCESSING, Submission.updated_at < stale)
        .values(status=SubmissionStatus.RECEIVED, updated_at=func.now())
        .returning(Submission.id)
    )
    found += [
        Requeue(
            i, "Processing stopped with no progress (the worker probably restarted); queued again."
        )
        for i in rows
    ]

    # 3. A scheduled retry that never ran.
    overdue = select(Submission.id).where(
        Submission.status == SubmissionStatus.FAILED,
        Submission.retry_at.is_not(None),
        Submission.retry_at < grace,
    )
    result = await session.execute(
        update(Submission)
        .where(Submission.id.in_(overdue.limit(BATCH).scalar_subquery()))
        .where(Submission.status == SubmissionStatus.FAILED, Submission.retry_at < grace)
        .values(retry_at=func.now())  # the token stays: only this retry may claim it
        .returning(Submission.id, Submission.retry_token)
    )
    found += [
        Requeue(i, "The scheduled retry did not run; queued it again.", token)
        for i, token in result.all()
    ]
    return found


async def sweep(session: AsyncSession) -> int:
    """One sweep. Returns how many submissions were queued again."""
    with pipeline_span("sweeper.sweep") as span:
        queued = await _sweep(session)
        span.set_attribute("queued", queued)
        return queued


async def _sweep(session: AsyncSession) -> int:
    removed = await upload_buffer.purge_expired()  # files nobody read in time
    if removed:
        logger.warning("Sweeper deleted %d expired upload file(s)", removed)
    found = await find_and_mark(session, datetime.now(UTC))
    if not found:
        return 0
    runs = {r.submission_id: await _running_reprocess(session, r.submission_id) for r in found}
    for item in found:
        record_step(
            session,
            submission_id=item.submission_id,
            step=StepName.PIPELINE,
            result=StepResult.WARNING,
            message=item.reason,
            output={"retry": item.retry_token is not None},
        )
    await session.commit()  # marked first: a crash now means the next sweep tries again

    queued = 0
    for item in found:
        try:
            await enqueue_submission(
                item.submission_id,
                reprocess_run_id=runs[item.submission_id],
                retry_token=item.retry_token,
            )
            queued += 1
        except Exception:
            logger.exception("Sweeper could not queue %s; will try next time", item.submission_id)
    logger.warning("Sweeper queued %d lost submission(s) again", queued)
    return queued
