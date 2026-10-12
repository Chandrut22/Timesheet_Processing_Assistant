"""Send email through SMTP.

Uses Python's built-in smtplib. Sending is blocking network I/O, so it runs in
a worker thread (asyncio.to_thread) and never freezes the async server.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from src.config.settings import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(Exception):
    """SMTP_USERNAME / SMTP_PASSWORD are not set."""


def _build_message(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    sender = settings.smtp_from_email or settings.smtp_username or ""
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)  # plain-text version (always include one)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def _send_blocking(message: EmailMessage) -> None:
    if not settings.smtp_username or settings.smtp_password is None:
        raise EmailNotConfiguredError("SMTP_USERNAME and SMTP_PASSWORD must be set.")
    password = settings.smtp_password.get_secret_value()
    context = ssl.create_default_context()

    if settings.smtp_use_ssl:  # port 465: TLS from the first byte
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_s,
            context=context,
        ) as server:
            server.login(settings.smtp_username, password)
            server.send_message(message)
        return

    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s
    ) as server:
        if settings.smtp_starttls:  # port 587: upgrade the plain connection to TLS
            server.starttls(context=context)
        server.login(settings.smtp_username, password)
        server.send_message(message)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Send one email. Raises on failure (callers decide whether to log or retry)."""
    await asyncio.to_thread(_send_blocking, _build_message(to, subject, text, html))
    logger.info("Email sent to %s: %s", to, subject)
