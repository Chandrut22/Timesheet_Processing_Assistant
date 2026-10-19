from celery import Celery

from src.config.settings import settings

celery_app = Celery("core", broker=settings.redis_url, include=["src.control.workers.tasks"])

celery_app.conf.update(
    # Redis is shared: every Celery key starts with "core:celery:"
    broker_transport_options={
        "global_keyprefix": f"{settings.redis_prefix}:celery:",
        # An unacknowledged job goes to another worker only after this long: longer
        # than any job may run (see the time limits below), so a running job is never
        # started twice.
        "visibility_timeout": settings.broker_visibility_timeout_seconds,
    },
    # The job stops itself at WORKER_JOB_TIMEOUT_SECONDS (processing_service); this hard
    # limit kills the worker process if the job is stuck where it cannot be stopped.
    task_time_limit=settings.worker_hard_time_limit_seconds,
    task_default_queue="timesheets",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # results live in Postgres, not in Celery
    task_acks_late=True,  # a job is removed from the queue only after it finished...
    task_reject_on_worker_lost=True,  # ...so a crashed worker's job is picked up again
    worker_prefetch_multiplier=1,  # long jobs (OCR, LLM): take one at a time
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    # Celery beat (service "core-beat") runs the sweeper: lost jobs are queued again.
    beat_schedule={
        "sweep-lost-work": {
            "task": "core.sweep",
            "schedule": float(settings.sweeper_interval_seconds),
            "options": {"expires": settings.sweeper_interval_seconds},  # never pile up
        }
    },
)
