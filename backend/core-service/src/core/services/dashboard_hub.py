"""One hub per API process: listens for change messages, builds ONE snapshot, and pushes
it to every connected browser, so N viewers cost one query round instead of N."""

import asyncio
import contextlib
import logging
import time
from typing import Any, cast

from src.config.settings import settings
from src.core.services.dashboard_service import build_snapshot
from src.data.clients.dashboard_hooks import CHANNEL
from src.data.clients.postgres import SessionLocal
from src.data.clients.redis import redis_client

logger = logging.getLogger(__name__)

DEBOUNCE_S = 0.3  # one pipeline run writes many rows; batch them into one refresh
FRESH_S = 2.0  # a snapshot this young is good enough for a newly connected viewer


class DashboardHub:
    def __init__(self) -> None:
        self._clients: set[asyncio.Queue[str | None]] = set()
        self._latest: str | None = None
        self._built_at = 0.0
        self._dirty = asyncio.Event()
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._listen(), name="dashboard-listen"),
            asyncio.create_task(self._refresh_loop(), name="dashboard-refresh"),
        ]

    async def stop(self) -> None:
        for q in list(self._clients):
            self._offer(q, None)  # tells every open stream to finish
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def subscribe(self) -> asyncio.Queue[str | None]:
        q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=1)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str | None]) -> None:
        self._clients.discard(q)

    async def current(self) -> str:
        """The latest snapshot (JSON text), built on demand if it is stale or missing."""
        async with self._lock:
            if self._latest is None or time.monotonic() - self._built_at > FRESH_S:
                await self._rebuild()
            assert self._latest is not None
            return self._latest

    async def _rebuild(self) -> None:  # callers hold self._lock
        async with SessionLocal() as session:
            payload = (await build_snapshot(session)).model_dump_json()
        self._built_at = time.monotonic()
        if payload == self._latest:
            return  # nothing visible changed: send nothing
        self._latest = payload
        for q in list(self._clients):
            self._offer(q, payload)

    @staticmethod
    def _offer(q: asyncio.Queue[str | None], item: str | None) -> None:
        # Keep only the newest item: a slow browser gets the latest picture, not a backlog.
        if q.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                q.get_nowait()
        q.put_nowait(item)

    async def _listen(self) -> None:
        while True:
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(CHANNEL)
                self._dirty.set()  # messages may have been missed while we were away
                try:
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            self._dirty.set()
                finally:
                    # aclose() has no type hints in some redis versions: call it untyped.
                    await cast(Any, pubsub).aclose()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Dashboard listener lost Redis; retrying in 2 s", exc_info=True)
                await asyncio.sleep(2)

    async def _refresh_loop(self) -> None:
        while True:
            # Safety net: refresh even if no message arrived within the poll time.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._dirty.wait(), timeout=settings.dashboard_poll_seconds)
            await asyncio.sleep(DEBOUNCE_S)
            self._dirty.clear()
            if not self._clients:
                continue  # nobody is watching: do not query
            try:
                async with self._lock:
                    await self._rebuild()
            except Exception:
                logger.exception("Could not rebuild the dashboard snapshot")
