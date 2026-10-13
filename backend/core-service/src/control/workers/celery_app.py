from celery import Celery

from src.config.settings import settings

celery_app = Celery("core", broker=settings.redis_url, include=["src.control.workers.tasks"])

celery_app.conf.update(
    # Redis is shared: every Celery key starts with "core:celery:"
    broker_transport_options={"global_keyprefix": f"{settings.redis_prefix}:celery:"},
    task_default_queue="timesheets",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # results live in Postgres, not in Celery
    task_acks_late=True,  # a job is removed from the queue only after it finished...
    task_reject_on_worker_lost=True,  # ...so a crashed worker's job is picked up again
    worker_prefetch_multiplier=1,  # long jobs (OCR, LLM): take one at a time
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)
