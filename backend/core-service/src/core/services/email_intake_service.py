"""One incoming email -> one submission, processed exactly like an upload.

  1. Unknown sender (not on any company's whitelist)      -> ignored, nothing saved
  2. Sender not verified by our mail server (SPF/DKIM)    -> ignored, nothing saved
  3. Same Message-ID seen before                          -> skipped (no double processing)
  4. Attachments -> documents; their bytes go to the Redis upload buffer
     (logos, invoices-as-images and unsupported files are recorded but never read)
  5. No readable attachment but text in the body          -> the body becomes the document
  6. Commit, then queue the submission for the worker

Unknown senders are not saved on purpose: anyone can send us email, and the
database should not fill up with spam."""

import hashlib
import logging
from enum import StrEnum
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.file_types import IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS, skip_reason
from src.constants.timesheet_status import DocumentStatus, SubmissionSource, SubmissionStatus
from src.control.workers.dispatch import enqueue_submission
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal
from src.data.models import Document, Submission
from src.data.repositories.company_repository import WhitelistRepository
from src.handlers.email.parser import Attachment, ParsedEmail

logger = logging.getLogger(__name__)

BODY_FILENAME = "email-body.txt"
MIN_BODY_CHARS = 20  # "Thanks" or a signature alone is not a timesheet


class IntakeOutcome(StrEnum):
    QUEUED = "queued"
    DUPLICATE = "duplicate (already received)"
    UNKNOWN_SENDER = "ignored: sender not on any whitelist"
    UNVERIFIED_SENDER = "ignored: sender failed SPF/DKIM/DMARC"
    EMPTY = "ignored: nothing to read (no attachment, body too short)"


def _safe_filename(raw: str) -> str:
    name = PurePath(raw.replace("\\", "/")).name  # drop any path in the name
    return name[:255] or "unnamed"


def _document_for(attachment: Attachment) -> tuple[Document, bool]:
    """Document row for one attachment, and whether its bytes should be read."""
    filename = _safe_filename(attachment.filename)
    extension = PurePath(filename).suffix.lower()
    data = attachment.data
    max_bytes = settings.max_upload_mb * 1024 * 1024

    reason: str | None
    if not data:
        reason = "The attachment is empty."
    elif len(data) > max_bytes:
        reason = f"Larger than {settings.max_upload_mb} MB."
    elif attachment.is_inline and extension in IMAGE_EXTENSIONS:
        reason = "Inline image skipped (logo or email signature)."
    else:
        reason = skip_reason(extension, len(data))

    document = Document(
        filename=filename,
        content_type=SUPPORTED_EXTENSIONS.get(extension, attachment.content_type)[:100],
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status=DocumentStatus.UNSUPPORTED if reason else DocumentStatus.PENDING,
        error=reason,
    )
    return document, reason is None


def _body_document(body: str) -> Document:
    """The email text itself, already 'read': the worker goes straight to extraction."""
    data = body.encode("utf-8")
    return Document(
        filename=BODY_FILENAME,
        content_type="text/plain",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status=DocumentStatus.PARSED,
        extracted_text=body,
    )


class EmailIntakeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _already_received(self, message_id: str) -> bool:
        found = await self.session.scalar(
            select(Submission.id).where(Submission.message_id == message_id).limit(1)
        )
        return found is not None

    async def accept(self, email: ParsedEmail) -> IntakeOutcome:
        company_id = (
            await WhitelistRepository(self.session).find_company_id_for_sender(email.from_email)
            if email.from_email
            else None
        )
        if company_id is None:
            logger.warning("Ignored email from %s: not on any whitelist", email.from_email or "?")
            return IntakeOutcome.UNKNOWN_SENDER
        if settings.email_require_sender_auth and not email.sender_auth_passed:
            logger.warning("Ignored email from %s: SPF/DKIM/DMARC did not pass", email.from_email)
            return IntakeOutcome.UNVERIFIED_SENDER
        if await self._already_received(email.message_id):
            return IntakeOutcome.DUPLICATE

        submission = Submission(
            source=SubmissionSource.EMAIL,
            status=SubmissionStatus.RECEIVED,
            company_id=company_id,
            sender_email=email.from_email[:255],
            subject=email.subject or None,
            body_text=email.body_text or None,
            message_id=email.message_id,
            received_at=email.received_at,
        )
        to_buffer: list[tuple[Document, bytes]] = []
        for attachment in email.attachments[: settings.email_max_attachments]:
            document, readable = _document_for(attachment)
            submission.documents.append(document)
            if readable:
                to_buffer.append((document, attachment.data))

        # Hours typed in the email itself (no timesheet file attached)
        if not to_buffer and len(email.body_text.strip()) >= MIN_BODY_CHARS:
            submission.documents.append(_body_document(email.body_text.strip()))

        if not submission.documents:
            return IntakeOutcome.EMPTY

        self.session.add(submission)
        try:
            await self.session.flush()  # ids are known now
        except IntegrityError:
            await self.session.rollback()  # another listener saved the same Message-ID first
            return IntakeOutcome.DUPLICATE
        for document, data in to_buffer:  # bytes go to Redis BEFORE the commit...
            await upload_buffer.put_file(document.id, data)
        await self.session.commit()  # ...so the worker never sees a row without its file
        await enqueue_submission(submission.id)
        logger.info(
            "Email from %s -> submission %s (%d document(s))",
            email.from_email,
            submission.id,
            len(submission.documents),
        )
        return IntakeOutcome.QUEUED


async def accept_email(email: ParsedEmail) -> str:
    """One session per email: a failure never leaves the next email in a broken session."""
    async with SessionLocal() as session:
        return await EmailIntakeService(session).accept(email)
