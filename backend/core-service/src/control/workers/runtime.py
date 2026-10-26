"""Celery tasks are plain functions; our code is async. Each worker process keeps ONE
event loop for its whole life, so SQLAlchemy's and Redis's connection pools (which
belong to a loop) are reused across tasks instead of breaking."""

import asyncio
import contextvars
from collections.abc import Coroutine
from typing import Any

from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
    worker_ready,
)

from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import flush_logs, setup_logging
from src.observability.metrics.setup import setup_metrics, shutdown_metrics
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

_runner: asyncio.Runner | None = None


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one task's coroutine on the process's event loop.

    Each call gets a fresh copy of the CURRENT context: without it, asyncio.Runner reuses
    the context of its first run, so every later job would still see the first job's
    trace (and any other context variable set then)."""
    global _runner
    if _runner is None:
        _runner = asyncio.Runner()
    return _runner.run(coro, context=contextvars.copy_context())


async def _close_clients() -> None:
    await engine.dispose()
    await redis_client.aclose()
    await upload_buffer.close()


@worker_process_init.connect
def _start_tracing(**_: Any) -> None:
    """Each worker process (after the fork) sets up its own log provider and tracing:
    a job continues the trace of the upload / email that queued it, and its log records
    carry that trace id. Tracing only if OTEL_ENABLED."""
    setup_logging()  # a new process: its own provider (and batch thread)
    setup_tracing(engine=engine, celery=True)
    setup_metrics("core-worker")  # only if OTEL_ENABLED and a collector endpoint is set


@worker_ready.connect
def _announce_vision(**_: Any) -> None:
    """Once per worker: say where page images go when the vision read is on."""
    from src.handlers.http_clients.vision_reader import log_destination

    log_destination()


@worker_process_shutdown.connect
def _shutdown(**_: Any) -> None:
    if _runner is not None:
        _runner.run(_close_clients())
        _runner.close()
    shutdown_metrics()
    shutdown_tracing()
    flush_logs()
