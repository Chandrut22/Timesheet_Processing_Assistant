"""A failed run: record it in plain words and decide whether to try again later."""

import logging
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    StepName,
    StepResult,
    SubmissionState,
    SubmissionStatus,
)
from src.core.services.activity_log import record_step, set_state
from src.core.services.failures import explain, plan_retry, technical_details
from src.core.services.reprocess import finish_run
from src.data.models import Submission

logger = logging.getLogger(__name__)


class RetryLater(Exception):  # noqa: N818 - a signal to the task, not an error
    """A temporary failure: the task should run again after delay_seconds, carrying the
    token (only that scheduled run may pick the submission up)."""

    def __init__(self, token: uuid.UUID, delay_seconds: int) -> None:
        super().__init__(f"retry in {delay_seconds}s")
        self.token = token
        self.delay_seconds = delay_seconds


async def record_failure(
    session: AsyncSession,
    submission_id: uuid.UUID,
    reprocess_run_id: uuid.UUID | None,
    attempt: int,
    exc: Exception,
) -> RetryLater | None:
    """Record the failure in plain words and decide: try again later, or stop.
    The technical error goes to the processing log only."""
    failure = explain(exc)
    most = settings.worker_max_attempts
    plan = plan_retry(
        failure,
        attempt,
        max_attempts=most,
        base_delay=settings.worker_retry_delay_seconds,
    )
    token = uuid.uuid4() if plan.retry else None
    if plan.retry and plan.retry_at is not None:
        reason = (
            f"{failure.message} Trying again automatically at "
            f"{plan.retry_at:%H:%M} UTC (run {attempt + 1} of {most})."
        )
    else:
        runs = f" after {attempt} runs" if 1 < attempt <= most else ""
        reason = f"{failure.message} Stopped{runs}. {failure.advice}"

    await session.execute(
        update(Submission)
        .where(Submission.id == submission_id)
        .values(
            status=SubmissionStatus.FAILED,
            error=reason,
            retry_at=plan.retry_at,
            retry_token=token,
        )
    )
    failed = await session.get(Submission, submission_id, populate_existing=True)
    if failed is not None:
        set_state(session, failed, SubmissionState.FAILED, reason=reason)
        record_step(
            session,
            submission_id=submission_id,
            step=StepName.PIPELINE,
            result=StepResult.ERROR,
            message=reason,
            input={"run": attempt, "max_runs": most},
            output={
                "temporary": failure.temporary,
                "retry_at": plan.retry_at.isoformat() if plan.retry_at else None,
            },
            error_details=technical_details(exc),
        )
    if reprocess_run_id is not None and not plan.retry:  # a retry keeps the run open
        await finish_run(session, reprocess_run_id, error=reason)
    await session.commit()

    if token is not None:
        logger.warning(
            "Submission %s failed (run %d of %d), retry in %ds: %s",
            submission_id,
            attempt,
            most,
            plan.delay_seconds,
            technical_details(exc, limit=300),
        )
        return RetryLater(token, plan.delay_seconds)
    logger.exception("Submission %s failed (run %d of %d)", submission_id, attempt, most)
    return None
