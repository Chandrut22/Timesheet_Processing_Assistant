"""Redis signals between core-service (the dashboard's "Check mail now") and core-email.

The two never call each other: core-service PUBLISHes a check request on CHECK_CHANNEL
and writes the request under result_key(id); the listener updates that key as it works
(queued -> running -> done / failed). The listener also keeps a heartbeat (STATUS_KEY)
so the API can tell whether it is running, and CatchUpLock lets only one catch-up (the
IDLE loop's or a manual one) read the mailbox at a time, so the cursor never races.

  core:imap:check_now          channel   {"request_id": "..."}
  core:imap:check:<id>         string    JSON, kept RESULT_TTL_S
  core:imap:status             hash      alive_at, enabled, connected, last_check_at,
  ... core:imap:catchup_lock       string    holder token, expires after LOCK_TTL_S
  core:imap:manual_cooldown    string    set NX with the cooldown as its expiry
"""

import asyncio
import contextlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from src.data.clients.redis import redis_key

CHECK_CHANNEL = redis_key("imap", "check_now")
STATUS_KEY = redis_key("imap", "status")
LOCK_KEY = redis_key("imap", "catchup_lock")
COOLDOWN_KEY = redis_key("imap", "manual_cooldown")
RESULT_TTL_S = 600
LOCK_TTL_S = (
    600  # a catch-up of one batch never takes this long; frees a dead holder's lock
)

_RELEASE = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


def result_key(request_id: str) -> str:
    return redis_key("imap", "check", request_id)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# The redis client's async methods are typed "Awaitable[T] | T", so callers pass Any.


async def read_result(redis: Any, request_id: str) -> dict[str, Any] | None:
    raw = await redis.get(result_key(request_id))
    return json.loads(raw) if raw else None


async def update_result(redis: Any, request_id: str, **fields: Any) -> None:
    """Merge fields into the request's record (and keep it RESULT_TTL_S longer)."""
    record = await read_result(redis, request_id) or {"request_id": request_id}
    record.update(fields)
    await redis.set(result_key(request_id), json.dumps(record), ex=RESULT_TTL_S)


async def write_status(redis: Any, **fields: Any) -> None:
    def text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)

    await redis.hset(STATUS_KEY, mapping={k: text(v) for k, v in fields.items()})


async def read_status(redis: Any) -> dict[str, str]:
    return dict(await redis.hgetall(STATUS_KEY))


class CatchUpLock:
    """Only one catch-up reads the mailbox at a time. Waits for the current holder; the
    expiry frees the lock if its holder died. Release only deletes our own token."""

    def __init__(
        self, redis: Any, *, wait_s: float = LOCK_TTL_S, poll_s: float = 0.25
    ) -> None:
        self.redis = redis
        self.wait_s = wait_s
        self.poll_s = poll_s
        self.token = uuid.uuid4().hex

    async def __aenter__(self) -> "CatchUpLock":
        deadline = time.monotonic() + self.wait_s
        while not await self.redis.set(LOCK_KEY, self.token, nx=True, ex=LOCK_TTL_S):
            if time.monotonic() >= deadline:
                raise TimeoutError("Another mailbox check is still running.")
            await asyncio.sleep(self.poll_s)
        return self

    async def __aexit__(self, *exc: object) -> None:
        with contextlib.suppress(Exception):  # Redis gone: the lock's expiry frees it
            await self.redis.eval(_RELEASE, 1, LOCK_KEY, self.token)
