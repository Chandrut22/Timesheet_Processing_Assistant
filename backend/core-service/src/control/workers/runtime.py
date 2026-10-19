"""Celery tasks are plain functions; our code is async. Each worker process keeps ONE
event loop for its whole life, so SQLAlchemy's and Redis's connection pools (which
belong to a loop) are reused across tasks instead of breaking."""

import asyncio
import contextvars
import logging
from collections.abc import Coroutine
from typing import Any

from celery.signals import (
    after_setup_logger,
    after_setup_task_logger,
    worker_process_init,
    worker_process_shutdown,
)

from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import add_trace_ids
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
    """Each worker process (after the fork) sets up its own tracing: a job continues
    the trace of the upload / email that queued it. Only if OTEL_ENABLED."""
    setup_tracing(engine=engine, celery=True)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _trace_ids_in_logs(logger: logging.Logger, **_: Any) -> None:
    add_trace_ids(logger)


@worker_process_shutdown.connect
def _shutdown(**_: Any) -> None:
    if _runner is not None:
        _runner.run(_close_clients())
        _runner.close()
    shutdown_tracing()
