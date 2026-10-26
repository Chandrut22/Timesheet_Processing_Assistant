"""Server-sent events (SSE): the live dashboard stream, GET /dashboard/stream.

The dashboard's first load and its fallback while the stream is down use
GET /dashboard (routes/dashboard.py); this stream pushes the same snapshot after every
visible change (see core/services/dashboard_hub.py)."""

import asyncio
import logging
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from src.api.rest.dependencies import Reviewer, bearer_scheme
from src.config.settings import settings
from src.core.services.dashboard_hub import DashboardHub

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_open_streams: Counter[uuid.UUID] = Counter()


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _expires_at(credentials: HTTPAuthorizationCredentials) -> float:
    # The Reviewer dependency already fully verified this token; here we only read its expiry.
    claims = jwt.decode(credentials.credentials, options={"verify_signature": False})
    return float(claims["exp"])


@router.get("/stream")
async def stream_dashboard(
    request: Request,
    principal: Reviewer,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> StreamingResponse:
    """Server-sent events: a `snapshot` event on connect and after every visible change,
    a comment heartbeat while idle, and a `reauth` event when the token expires (the
    browser then reconnects with a fresh one)."""
    assert credentials is not None  # Reviewer already rejected anonymous callers
    if _open_streams[principal.id] >= settings.dashboard_max_streams_per_user:
        raise HTTPException(status_code=429, detail="Too many open dashboards. Close another tab.")

    hub: DashboardHub = request.app.state.dashboard_hub
    expires_at = _expires_at(credentials)

    async def events() -> AsyncIterator[str]:
        _open_streams[principal.id] += 1
        queue = hub.subscribe()
        try:
            yield "retry: 3000\n\n"
            try:
                yield _sse("snapshot", await hub.current())
            except Exception:
                logger.exception("Dashboard snapshot failed")
                yield _sse("error", '{"detail":"Dashboard unavailable"}')
                return
            while True:
                remaining = expires_at - time.time()
                if remaining <= 0:
                    yield _sse("reauth", "{}")
                    return
                try:
                    payload = await asyncio.wait_for(
                        queue.get(), timeout=min(settings.dashboard_heartbeat_seconds, remaining)
                    )
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if payload is None:  # the server is shutting down
                    return
                yield _sse("snapshot", payload)
        finally:
            hub.unsubscribe(queue)
            _open_streams[principal.id] -= 1
            if _open_streams[principal.id] <= 0:
                del _open_streams[principal.id]

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
