"""The email listener: waits for new mail with IMAP IDLE and turns each email into a
submission. Run exactly ONE of these (docker compose service "core-email"):

    python -m src.control.workers.email_listener
"""

import asyncio
import logging

from imap_tools.errors import MailboxLoginError

from src.config.settings import settings
from src.core.services.email_intake_service import accept_email, record_failed_email
from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.handlers.email.imap_source import FETCH_LIMIT, ImapSource
from src.handlers.email.listener import Cursor, process_new_mail
from src.observability.logging.setup import configure_logging
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

logger = logging.getLogger("email_listener")


async def _catch_up(source: ImapSource, cursor: Cursor) -> None:
    """Read everything new; a full batch means there is more waiting."""
    while (
        await process_new_mail(
            source, cursor, accept_email, batch_limit=FETCH_LIMIT, give_up=record_failed_email
        )
        >= FETCH_LIMIT
    ):
        pass


async def run() -> None:
    cursor = Cursor(redis_client)
    backoff = 5
    while True:
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
                await _catch_up(source, cursor)  # mail that came while we were away
                while True:
                    # IDLE: the server tells us when mail arrives. The timeout is a safety
                    # net (and keeps the connection alive; Gmail drops IDLE after ~29 min).
                    if await asyncio.to_thread(source.wait, settings.email_idle_timeout):
                        logger.info("Mailbox changed")
                    await _catch_up(source, cursor)
            finally:
                await asyncio.to_thread(source.__exit__, None, None, None)
        except MailboxLoginError:
            logger.error(
                "IMAP login failed. Check IMAP_USER / IMAP_PASSWORD (Gmail: App Password)."
            )
        except Exception:
            logger.exception("Email listener error")
        logger.info("Reconnecting in %s s", backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 300)


async def main() -> None:
    configure_logging(settings.log_level)
    setup_tracing(engine=engine, celery=True)  # only if OTEL_ENABLED
    if not settings.email_enabled:
        logger.warning("EMAIL_ENABLED is false: the email listener is not running.")
        return
    if not (settings.imap_host and settings.imap_user and settings.imap_password):
        logger.error("Set IMAP_HOST, IMAP_USER and IMAP_PASSWORD to read email.")
        return
    try:
        await run()
    finally:
        await engine.dispose()
        await redis_client.aclose()
        await upload_buffer.close()
        shutdown_tracing()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
