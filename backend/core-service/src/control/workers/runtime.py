"""Celery tasks are plain functions; our code is async. Each worker process keeps ONE
event loop for its whole life, so SQLAlchemy's and Redis's connection pools (which
belong to a loop) are reused across tasks instead of breaking."""

import asyncio
from collections.abc import Coroutine
from typing import Any

from celery.signals import worker_process_shutdown

from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client

_runner: asyncio.Runner | None = None


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    global _runner
    if _runner is None:
        _runner = asyncio.Runner()
    return _runner.run(coro)


async def _close_clients() -> None:
    await engine.dispose()
    await redis_client.aclose()
    await upload_buffer.close()


@worker_process_shutdown.connect
def _shutdown(**_: Any) -> None:
    if _runner is not None:
        _runner.run(_close_clients())
        _runner.close()
