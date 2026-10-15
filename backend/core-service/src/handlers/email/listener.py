"""Find mail that arrived since the last check and hand each email to the intake.

Where we are in the mailbox is a cursor in Redis: (UIDVALIDITY, last UID handled).
The database (submissions.message_id is unique) is what really stops an email from
being processed twice, so re-reading a few emails after a crash is harmless."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from email.message import Message
from typing import Protocol

from redis.asyncio import Redis

from src.config.settings import settings
from src.data.clients.redis import redis_key
from src.handlers.email.parser import ParsedEmail, parse_message

logger = logging.getLogger(__name__)

CURSOR_KEY = redis_key("imap", "cursor")  # hash: uidvalidity, last_uid


class MailSource(Protocol):
    """What the listener needs from a mailbox (ImapSource, or a fake in tests)."""

    def status(self) -> tuple[int, int]: ...  # (UIDVALIDITY, UIDNEXT)
    def fetch_from_uid(self, start_uid: int) -> list[tuple[int, Message]]: ...
    def fetch_since(self, day: date) -> list[tuple[int, Message]]: ...


Intake = Callable[[ParsedEmail], Awaitable[str]]  # returns what happened, for the log


class Cursor:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get(self) -> tuple[int | None, int]:
        data = await self.redis.hgetall(CURSOR_KEY)  
        if not data:
            return None, 0
        return int(data["uidvalidity"]), int(data["last_uid"])

    async def set(self, uidvalidity: int, last_uid: int) -> None:
        await self.redis.hset(  
            CURSOR_KEY, mapping={"uidvalidity": uidvalidity, "last_uid": last_uid}
        )


async def process_new_mail(
    source: MailSource, cursor: Cursor, intake: Intake, *, batch_limit: int
) -> int:
    """Hand every email since the cursor to `intake`. Returns how many were fetched
    (== batch_limit means there may be more: call again)."""
    validity, uidnext = await asyncio.to_thread(source.status)
    saved_validity, last_uid = await cursor.get()
    today = datetime.now(UTC).date()

    if saved_validity is None:
        if settings.email_start_from == "new":
            await cursor.set(validity, uidnext - 1)
            logger.info("First run: watching for mail from UID %s on", uidnext)
            return 0
        logger.info("First run: reading the last %s day(s) of mail", settings.email_backfill_days)
        since = today - timedelta(days=settings.email_backfill_days)
        messages = await asyncio.to_thread(source.fetch_since, since)
        resync = True
    elif saved_validity != validity:
        # The server renumbered the folder, so the old UIDs mean nothing now.
        logger.warning(
            "UIDVALIDITY changed (%s -> %s); re-reading 2 days", saved_validity, validity
        )
        messages = await asyncio.to_thread(source.fetch_since, today - timedelta(days=2))
        resync = True
    else:
        if uidnext - 1 <= last_uid:
            return 0  # nothing new
        messages = await asyncio.to_thread(source.fetch_from_uid, last_uid + 1)
        resync = False

    highest = 0 if resync else last_uid
    for uid, msg in messages:
        if not resync and uid <= last_uid:
            continue  # "n:*" returns the last email even when nothing is newer
        email = parse_message(msg, fallback_id=f"<uid-{validity}-{uid}@imap.local>")
        outcome = await intake(email)  # raises on DB/Redis trouble: cursor stays put, retry later
        logger.info("UID %s from %s: %s", uid, email.from_email or "?", outcome)
        highest = max(highest, uid)
        if not resync:
            await cursor.set(validity, highest)  # move forward after each email

    if resync:
        full_batch = len(messages) >= batch_limit
        await cursor.set(validity, highest if full_batch else max(highest, uidnext - 1))
    return len(messages)
