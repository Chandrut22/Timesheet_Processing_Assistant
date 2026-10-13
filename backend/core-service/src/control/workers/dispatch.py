import asyncio
import uuid


async def enqueue_submission(submission_id: uuid.UUID) -> None:
    """Queue a submission for the worker. .delay() is a blocking Redis call, so it
    runs in a thread and never stalls the API's event loop."""
    from src.control.workers.tasks import process_submission  # imported here: avoids a cycle

    await asyncio.to_thread(process_submission.delay, str(submission_id))
