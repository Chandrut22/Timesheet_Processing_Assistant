"""Find mail that arrived since the last check and hand each email to the intake.

Where we are in the mailbox is a cursor in Redis: (UIDVALIDITY, last UID handled).
The database (submissions.message_id is unique) is what really stops an email from
being processed twice, so re-reading a few emails after a crash is harmless.

When an email cannot be saved, the cursor stays before it and it is tried again on the
next check. If the cause is temporary (database or Redis down) that repeats until the
service is back. Any other error (a broken email, data the database refuses) is
counted: after email_max_intake_failures tries the email is recorded as failed and
skipped, so one bad email can never block the rest of the inbox.

With IMAP_MARK_AS_READ=true an email is marked as read once the intake has saved it
(as a submission, as ignored, or found to be a repeat). Never before: a crash or a
failed save leaves it unread and it is tried again. A skipped (broken) email is left
unread, so a person notices it. Failing to mark is only logged: the email is saved."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from email.message import Message
from typing import Protocol

from redis.asyncio import Redis

from src.config.settings import settings
from src.core.services.failures import explain, technical_details
from src.data.clients.redis import redis_key
from src.handlers.email.parser import ParsedEmail, parse_message

logger = logging.getLogger(__name__)

CURSOR_KEY = redis_key("imap", "cursor")  # hash: uidvalidity, last_uid
FAILURES_KEY = redis_key("imap", "failures")  # hash: "<uidvalidity>:<uid>" -> failed tries
FAILURES_TTL = 7 * 24 * 3600


class MailSource(Protocol):
    """What the listener needs from a mailbox (ImapSource, or a fake in tests)."""

    def status(self) -> tuple[int, int]: ...  # (UIDVALIDITY, UIDNEXT)
    def fetch_from_uid(self, start_uid: int) -> list[tuple[int, Message]]: ...
    def fetch_since(self, day: date) -> list[tuple[int, Message]]: ...
    def mark_read(self, uid: int) -> None: ...  # set the \Seen flag on one email


Intake = Callable[[ParsedEmail], Awaitable[str]]  # returns what happened, for the log
# Called when an email is skipped after too many failures: (email or None, ref, reason).
GiveUp = Callable[[ParsedEmail | None, str, str], Awaitable[None]]


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

    async def failed(self, ref: str) -> int:
        """Count one more failed try for this email; returns the count."""
        count = int(await self.redis.hincrby(FAILURES_KEY, ref, 1))
        await self.redis.expire(FAILURES_KEY, FAILURES_TTL)
        return count

    async def forget(self, ref: str) -> None:
        await self.redis.hdel(FAILURES_KEY, ref)


async def _mark_read(source: MailSource, uid: int) -> bool:
    """Mark one saved email as read; False (and a warning) when the mailbox refuses."""
    try:
        await asyncio.to_thread(source.mark_read, uid)
    except Exception as exc:
        logger.warning("UID %s was saved but could not be marked as read: %s", uid, exc)
        return False
    return True


async def _handle(
    uid: int,
    msg: Message,
    ref: str,
    cursor: Cursor,
    intake: Intake,
    give_up: GiveUp | None,
    source: MailSource | None = None,
) -> None:
    """Parse and save one email. Raises when it should be tried again later; returns
    when it is done (saved, or skipped for good after too many failures). `source` is
    given when saved emails should be marked as read."""
    email: ParsedEmail | None = None
    try:
        email = parse_message(msg, fallback_id=f"<uid-{ref}@imap.local>")
        outcome = await intake(email)
    except Exception as exc:
        failure = explain(exc)
        if failure.temporary:  # database / Redis down: wait for it, count nothing
            raise
        tries = await cursor.failed(ref)
        if tries < settings.email_max_intake_failures:
            logger.warning("UID %s could not be saved (try %d): %s", uid, tries, exc)
            raise
        reason = (
            f"This email could not be saved after {tries} tries and was skipped "
            f"so the rest of the inbox can be read. Details: {technical_details(exc, 500)}"
        )
        logger.error("UID %s skipped: %s", uid, reason)
        if give_up is not None:
            try:
                await give_up(email, ref, reason)
            except Exception:
                logger.exception("Could not record the skipped email UID %s", uid)
        await cursor.forget(ref)
        return
    await cursor.forget(ref)
    marked = source is not None and await _mark_read(source, uid)
    logger.info(
        "UID %s from %s: %s%s",
        uid,
        email.from_email or "?",
        outcome,
        ", marked as read" if marked else "",
    )


async def process_new_mail(
    source: MailSource,
    cursor: Cursor,
    intake: Intake,
    *,
    batch_limit: int,
    give_up: GiveUp | None = None,
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
    marker = source if settings.imap_mark_as_read else None
    for uid, msg in messages:
        if not resync and uid <= last_uid:
            continue  # "n:*" returns the last email even when nothing is newer
        # Raises when the email must be tried again: the cursor stays before it.
        await _handle(uid, msg, f"{validity}-{uid}", cursor, intake, give_up, marker)
        highest = max(highest, uid)
        if not resync:
            await cursor.set(validity, highest)  # move forward after each email

    if resync:
        full_batch = len(messages) >= batch_limit
        await cursor.set(validity, highest if full_batch else max(highest, uidnext - 1))
    return len(messages)
