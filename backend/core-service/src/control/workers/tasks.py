import uuid

from celery import Task

from src.control.workers.celery_app import celery_app
from src.control.workers.runtime import run_async
from src.core.services.processing_service import RetryLater, process_submission_by_id
from src.core.services.sweeper import sweep
from src.data.clients.postgres import SessionLocal


@celery_app.task(name="core.process_submission", bind=True, max_retries=None)
def process_submission(
    self: "Task[..., None]",  # quoted: the stubs are generic, the real class is not
    submission_id: str,
    reprocess_run_id: str | None = None,
    retry_token: str | None = None,
) -> None:
    """Process one submission. After a temporary failure (AI model, database or Redis
    unreachable) the processing service schedules the next run: this re-queues the task
    with a delay and the retry token. How many runs are allowed lives in the database
    (submissions.attempts, worker_max_attempts), so Celery's own limit is off."""
    try:
        run_async(
            process_submission_by_id(
                uuid.UUID(submission_id),
                reprocess_run_id=uuid.UUID(reprocess_run_id)
                if reprocess_run_id
                else None,
                retry_token=uuid.UUID(retry_token) if retry_token else None,
            )
        )
    except RetryLater as later:
        raise self.retry(
            args=(submission_id, reprocess_run_id, str(later.token)),
            countdown=later.delay_seconds,
        ) from later


async def _sweep() -> int:
    async with SessionLocal() as session:
        return await sweep(session)


@celery_app.task(name="core.sweep")
def sweep_lost_work() -> int:
    """Queue again the submissions whose job was lost (see sweeper.py). Run by beat."""
    return run_async(_sweep())
