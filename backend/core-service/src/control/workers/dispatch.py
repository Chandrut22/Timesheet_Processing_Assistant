import asyncio
import logging
import uuid

from src.control.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def enqueue_submission(
    submission_id: uuid.UUID,
    *,
    reprocess_run_id: uuid.UUID | None = None,
    retry_token: uuid.UUID | None = None,
) -> None:
    """Queue a submission for the worker, by task name: the API never imports the
    worker's code (Docling, LLM). send_task is a blocking Redis call, so it runs in a
    thread. reprocess_run_id is set when the job is a reprocess (see reprocess_runs);
    retry_token when it is a scheduled retry (only that run may claim the
    submission)."""
    args = [
        str(submission_id),
        str(reprocess_run_id) if reprocess_run_id else None,
        str(retry_token) if retry_token else None,
    ]
    await asyncio.to_thread(celery_app.send_task, "core.process_submission", args=args)


async def enqueue_or_leave_for_sweeper(submission_id: uuid.UUID) -> bool:
    """Queue a submission that is ALREADY committed. If the queue (Redis) is down, the
    row stays "received" and the sweeper queues it once Redis is back, so the caller
    (an upload, an email) still succeeds. Returns whether it was queued now."""
    try:
        await enqueue_submission(submission_id)
    except Exception:
        logger.exception(
            "Could not queue submission %s now; the sweeper will queue it later",
            submission_id,
        )
        return False
    return True
