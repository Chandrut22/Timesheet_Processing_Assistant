import uuid

from src.control.workers.celery_app import celery_app
from src.control.workers.runtime import run_async
from src.core.services.processing_service import process_submission_by_id


@celery_app.task(name="core.process_submission")
def process_submission(submission_id: str) -> None:
    run_async(process_submission_by_id(uuid.UUID(submission_id)))
