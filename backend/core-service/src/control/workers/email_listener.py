"""The email listener: waits for new mail with IMAP IDLE and turns each email into a
submission. Run exactly ONE of these (docker compose service "core-email"):

    python -m src.control.workers.email_listener

It also answers the dashboard's "Check mail now" (core-service PUBLISHes on Redis, see
data/clients/mailbox_signals.py):
  - connected: a short SECOND connection reads the mailbox at once (a command cannot be
    sent on the connection that is in IDLE) and the result goes back through Redis;
  - waiting to reconnect: the wait ends at once and the reconnect's catch-up answers.
Every catch-up holds CatchUpLock, so the IDLE loop and a manual check never read the
mailbox (and move the cursor) at the same time. A heartbeat in Redis tells the API
whether the listener is running and what its last check found.
"""

import asyncio
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, cast

from imap_tools.errors import MailboxLoginError

from src.config.settings import settings
from src.core.services.email_intake_service import accept_email, record_failed_email
from src.data.clients import upload_buffer
from src.data.clients.mailbox_signals import (
    CHECK_CHANNEL,
    CatchUpLock,
    now_iso,
    update_result,
    write_status,
)
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.handlers.email.imap_source import (
    FETCH_LIMIT,
    ImapSource,
    MailConnectionLostError,
)
from src.handlers.email.listener import Cursor, process_new_mail
from src.handlers.email.parser import ParsedEmail
from src.observability.logging.setup import flush_logs, setup_logging
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

logger = logging.getLogger("email_listener")

RECONNECT_AFTER_DROP_S = 2  # a working connection dropped: reconnect almost at once
QUICK_RECONNECT_GAP_S = 60  # ... unless the last quick reconnect was this recent
MAX_BACKOFF_S = 300
HEARTBEAT_EVERY_S = 60  # while waiting to reconnect (an IDLE round beats on its own)


def _bucket(outcome: str) -> str:
    """IntakeOutcome text -> queued / duplicates / ignored."""
    if outcome.startswith("ignored"):
        return "ignored"
    if outcome.startswith("duplicate"):
        return "duplicates"
    return "queued"


def summary(counts: Counter[str]) -> dict[str, int]:
    found = sum(counts.values())
    return {
        "found": found,
        "queued": counts["queued"],
        "ignored": counts["ignored"],
        "duplicates": counts["duplicates"],
        "failed": counts["failed"],
    }


async def _catch_up(source: ImapSource, cursor: Cursor) -> Counter[str]:
    """Read everything new (a full batch means there is more waiting), under the lock.
    Returns how many emails ended each way."""
    counts: Counter[str] = Counter()

    async def intake(email: ParsedEmail) -> str:
        outcome = str(await accept_email(email))
        counts[_bucket(outcome)] += 1
        return outcome

    async def give_up(email: ParsedEmail | None, ref: str, reason: str) -> None:
        counts["failed"] += 1
        await record_failed_email(email, ref, reason)

    async with CatchUpLock(redis_client):
        while (
            await process_new_mail(
                source, cursor, intake, batch_limit=FETCH_LIMIT, give_up=give_up
            )
            >= FETCH_LIMIT
        ):
            pass
    return counts


async def _beat(**fields: Any) -> None:
    """Heartbeat for the API. A Redis problem is only logged: it never stops the
    inbox."""
    try:
        await write_status(
            redis_client,
            alive_at=time.time(),
            enabled=True,
            mailbox=settings.imap_user,
            **fields,
        )
    except Exception as exc:
        logger.debug("Heartbeat not written: %s", exc)


async def _checked(counts: Counter[str] | None) -> None:
    """A finished catch-up: the heartbeat records when and what it found."""
    s = summary(counts or Counter())
    await _beat(
        connected=True,
        last_check_at=now_iso(),
        last_found=s["found"],
        last_queued=s["queued"],
        last_ignored=s["ignored"],
        last_error="",
    )


@dataclass
class ManualChecks:
    """State shared by the IDLE loop and the "Check mail now" watcher."""

    connected: bool = False
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    pending: list[str] = field(default_factory=list)  # asked while not connected
    tasks: set["asyncio.Task[None]"] = field(default_factory=set)

    async def resolve(self, counts: Counter[str] | None) -> None:
        """The reconnect's catch-up answers the requests made while disconnected."""
        for request_id in self.pending:
            await update_result(
                redis_client,
                request_id,
                state="done",
                finished_at=now_iso(),
                **summary(counts or Counter()),
            )
        self.pending.clear()
        self.wake.clear()  # answered: the next reconnect wait must not end at once

    async def fail(self, reason: str) -> None:
        for request_id in self.pending:
            await update_result(
                redis_client,
                request_id,
                state="failed",
                finished_at=now_iso(),
                error=reason,
            )
        self.pending.clear()


async def manual_check(request_id: str, cursor: Cursor) -> None:
    """One "Check mail now" while the IDLE connection is busy: a second connection."""
    await update_result(redis_client, request_id, state="running", started_at=now_iso())
    try:
        source = await asyncio.to_thread(ImapSource().__enter__)
        try:
            counts = await _catch_up(source, cursor)
        finally:
            await asyncio.to_thread(source.__exit__, None, None, None)
    except Exception as exc:
        logger.warning("Manual mailbox check failed: %s", exc)
        await update_result(
            redis_client,
            request_id,
            state="failed",
            finished_at=now_iso(),
            error=f"Could not read the mailbox: {exc}"[:500],
        )
        return
    await update_result(
        redis_client, request_id, state="done", finished_at=now_iso(), **summary(counts)
    )
    await _checked(counts)
    logger.info("Manual mailbox check %s: %s", request_id, summary(counts))


async def handle_request(raw: str, checks: ManualChecks, cursor: Cursor) -> None:
    try:
        request_id = str(json.loads(raw)["request_id"])
    except (ValueError, KeyError, TypeError):
        logger.warning("Ignored a malformed mailbox check request: %r", raw)
        return
    if checks.connected:
        task = asyncio.create_task(manual_check(request_id, cursor))
        checks.tasks.add(task)
        task.add_done_callback(checks.tasks.discard)
    else:
        checks.pending.append(request_id)
        await update_result(
            redis_client,
            request_id,
            state="running",
            started_at=now_iso(),
            note="Reconnecting to the mailbox first",
        )
        checks.wake.set()  # end the reconnect wait now


async def _watch_requests(checks: ManualChecks, cursor: Cursor) -> None:
    """Subscribed to CHECK_CHANNEL for as long as the listener runs."""
    while True:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(CHECK_CHANNEL)
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        await handle_request(message["data"], checks, cursor)
            finally:
                await cast(Any, pubsub).aclose()  # untyped in some redis versions
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Lost Redis for manual checks; retrying in 2 s", exc_info=True
            )
            await asyncio.sleep(2)


async def _sleep_or_wake(checks: ManualChecks, seconds: float) -> None:
    """The reconnect wait: ends early on "Check mail now", beats every minute."""
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        try:
            await asyncio.wait_for(
                checks.wake.wait(), timeout=min(left, HEARTBEAT_EVERY_S)
            )
        except TimeoutError:
            await _beat(connected=False)
            continue
        logger.info("Mailbox check requested: reconnecting now")
        break
    checks.wake.clear()


def next_delay(
    exc: BaseException, healthy_before: bool, backoff: int, since_last_quick: float
) -> int:
    """Seconds before reconnecting. A dropped connection that was working (healthy) gets
    a quick reconnect, at most once a minute; anything else (login refused, database or
    Redis down, drops in a row) waits `backoff`, which grows 5 s, 10 s, ... up to 5
    min."""
    if (
        isinstance(exc, MailConnectionLostError)
        and healthy_before
        and since_last_quick >= QUICK_RECONNECT_GAP_S
    ):
        return RECONNECT_AFTER_DROP_S
    return backoff


async def run() -> None:
    cursor = Cursor(redis_client)
    checks = ManualChecks()
    watcher = asyncio.create_task(
        _watch_requests(checks, cursor), name="mailbox-checks"
    )
    backoff = 5
    last_quick = 0.0  # monotonic time of the last quick reconnect
    try:
        while True:
            healthy = False  # becomes True once connected and caught up
            reason = ""
            try:
                source = await asyncio.to_thread(ImapSource().__enter__)
                try:
                    logger.info(
                        "Connected to %s as %s, folder %s",
                        settings.imap_host,
                        settings.imap_user,
                        settings.imap_folder,
                    )
                    backoff = 5
                    counts = await _catch_up(
                        source, cursor
                    )  # mail that came while away
                    healthy = True
                    checks.connected = True
                    await _checked(counts)
                    await checks.resolve(counts)
                    while True:
                        # IDLE: the server tells us when mail arrives. The timeout is a
                        # safety net (and keeps the connection alive; Gmail drops IDLE
                        # after ~29 min).
                        if await asyncio.to_thread(
                            source.wait, settings.email_idle_timeout
                        ):
                            logger.info("Mailbox changed")
                        counts = await _catch_up(source, cursor)
                        await _checked(counts)
                finally:
                    checks.connected = False
                    await asyncio.to_thread(source.__exit__, None, None, None)
            except MailboxLoginError as exc:
                logger.error(
                    "IMAP login failed. Check IMAP_USER / IMAP_PASSWORD (Gmail: App "
                    "Password)."
                )
                reason = "IMAP login failed: check IMAP_USER / IMAP_PASSWORD."
                delay = next_delay(exc, healthy, backoff, time.monotonic() - last_quick)
            except MailConnectionLostError as exc:
                # One line, no traceback: the network or Gmail closed the connection.
                # Nothing is lost: after reconnecting, the listener reads everything it
                # missed.
                logger.warning("Mail server connection lost (%s)", exc)
                reason = f"Mail server connection lost ({exc})"
                delay = next_delay(exc, healthy, backoff, time.monotonic() - last_quick)
            except Exception as exc:
                logger.exception("Email listener error")
                reason = f"Email listener error: {exc}"
                delay = next_delay(exc, healthy, backoff, time.monotonic() - last_quick)
            await _beat(connected=False, last_error=reason[:500])
            if checks.pending and not healthy:
                await checks.fail(reason or "Could not connect to the mailbox.")
            if delay == RECONNECT_AFTER_DROP_S:
                last_quick = time.monotonic()
            else:
                backoff = min(backoff * 2, MAX_BACKOFF_S)
            logger.info("Reconnecting in %s s", delay)
            await _sleep_or_wake(checks, delay)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, *checks.tasks, return_exceptions=True)


async def main() -> None:
    setup_logging()  # every log record goes through OpenTelemetry
    setup_tracing(engine=engine, celery=True)  # only if OTEL_ENABLED
    if not settings.email_enabled:
        logger.warning("EMAIL_ENABLED is false: the email listener is not running.")
        await write_status(redis_client, enabled=False, alive_at=time.time())
        return
    if not (settings.imap_host and settings.imap_user and settings.imap_password):
        logger.error("Set IMAP_HOST, IMAP_USER and IMAP_PASSWORD to read email.")
        await _beat(
            connected=False,
            last_error="IMAP_HOST, IMAP_USER and IMAP_PASSWORD are not set.",
        )
        return
    try:
        await run()
    finally:
        await engine.dispose()
        await redis_client.aclose()
        await upload_buffer.close()
        shutdown_tracing()
        flush_logs()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
