import asyncio
import uuid

from src.control.workers.celery_app import celery_app


async def enqueue_submission(
    submission_id: uuid.UUID, *, reprocess_run_id: uuid.UUID | None = None
) -> None:
    """Queue a submission for the worker, by task name: the API never imports the worker's
    code (Docling, LLM). send_task is a blocking Redis call, so it runs in a thread.
    reprocess_run_id is set when the job is a reprocess (see reprocess_runs)."""
    args = [str(submission_id)]
    if reprocess_run_id is not None:
        args.append(str(reprocess_run_id))
    await asyncio.to_thread(celery_app.send_task, "core.process_submission", args=args)
