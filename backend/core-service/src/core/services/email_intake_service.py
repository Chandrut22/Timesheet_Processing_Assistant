"""One incoming email -> one submission, processed exactly like an upload.

  1. Same Message-ID seen before                          -> skipped (no double processing)
  2. Unknown sender (not on any company's whitelist)      -> saved as Ignored, never read
  3. Sender not verified by our mail server (SPF/DKIM)    -> saved as Ignored, never read
  4. Attachments -> documents; their bytes go to the upload store (disk)
     (logos, invoices-as-images and unsupported files are recorded but never read)
  5. No readable attachment but text in the body          -> the body becomes the document
  6. Commit, then queue the submission for the worker (if the queue is down, the
     sweeper queues it later: the email is never lost or stuck)

Every email gets a record (sender, subject, received time, attachments) and a state,
as the use case requires. For ignored emails only that metadata is kept: no body text
and no file bytes."""

import hashlib
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.file_types import IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS, skip_reason
from src.constants.timesheet_status import (
    DocumentStatus,
    StepName,
    StepResult,
    SubmissionSource,
    SubmissionState,
    SubmissionStatus,
)
from src.control.workers.dispatch import enqueue_or_leave_for_sweeper
from src.core.services.activity_log import record_step, set_state
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal
from src.data.models import Document, Submission
from src.data.repositories.company_repository import WhitelistRepository
from src.handlers.email.parser import Attachment, ParsedEmail
from src.observability.tracing.spans import pipeline_span, set_attributes

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
        if await self._already_received(email.message_id):
            return IntakeOutcome.DUPLICATE

        company_id = (
            await WhitelistRepository(self.session).find_company_id_for_sender(email.from_email)
            if email.from_email
            else None
        )

        outcome = IntakeOutcome.QUEUED
        ignore_reason = None

        if company_id is None:
            outcome = IntakeOutcome.UNKNOWN_SENDER
            ignore_reason = "The sender is not on any company's whitelist."
        elif settings.email_require_sender_auth and not email.sender_auth_passed:
            outcome = IntakeOutcome.UNVERIFIED_SENDER
            ignore_reason = "The sender could not be verified (SPF/DKIM/DMARC did not pass)."

        submission = Submission(
            source=SubmissionSource.EMAIL,
            status=(SubmissionStatus.IGNORED if ignore_reason else SubmissionStatus.RECEIVED),
            company_id=company_id,
            sender_email=(email.from_email or "")[:255] or None,
            subject=email.subject or None,
            body_text=(None if ignore_reason else (email.body_text or None)),
            message_id=email.message_id,
            received_at=email.received_at,
        )

        documents: list[Document] = []
        to_buffer: list[tuple[Document, bytes]] = []

        for attachment in email.attachments[: settings.email_max_attachments]:
            document, readable = _document_for(attachment)

            if ignore_reason:
                document.status = DocumentStatus.UNSUPPORTED
                document.error = "Not read: the email was ignored."
            elif readable:
                to_buffer.append((document, attachment.data))

            submission.documents.append(document)
            documents.append(document)

        # Use the email body only when no readable attachment exists.
        if not ignore_reason and not to_buffer:
            body = (email.body_text or "").strip()

            if len(body) >= MIN_BODY_CHARS:
                body_document = _body_document(body)
                submission.documents.append(body_document)
                documents.append(body_document)
            else:
                outcome = IntakeOutcome.EMPTY
                ignore_reason = "No timesheet attachment and no timesheet text in the email."
                submission.status = SubmissionStatus.IGNORED

        self.session.add(submission)

        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            return IntakeOutcome.DUPLICATE

        # Capture scalar values before any commit.
        submission_id = submission.id
        set_attributes(submission_id=submission_id)
        document_count = len(documents)

        set_state(
            self.session,
            submission,
            SubmissionState.RECEIVED,
            first=True,
        )

        if ignore_reason:
            set_state(
                self.session,
                submission,
                SubmissionState.IGNORED,
                reason=ignore_reason,
            )

        record_step(
            self.session,
            submission_id=submission_id,
            step=StepName.COLLECT,
            result=(StepResult.WARNING if ignore_reason else StepResult.SUCCESS),
            message=(ignore_reason or f"Email received with {document_count} document(s)"),
            input={
                "sender": email.from_email,
                "subject": email.subject,
                "attachments": len(email.attachments),
                "sender_verified": email.sender_auth_passed,
            },
            output={
                "company_id": (str(company_id) if company_id else None),
                "documents": [
                    {
                        "file": document.filename,
                        "status": document.status,
                        "reason": document.error,
                    }
                    for document in documents
                ],
            },
        )

        try:
            for document, data in to_buffer:
                await upload_buffer.put_file(document.id, data)

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

        if ignore_reason:
            logger.warning(
                "Ignored email from %s: %s",
                email.from_email or "?",
                ignore_reason,
            )
            return outcome

        # Saved already: if the queue is down the sweeper queues it later, and this email
        # still counts as handled (the listener moves on).
        await enqueue_or_leave_for_sweeper(submission_id)

        logger.info(
            "Email from %s -> submission %s (%d document(s))",
            email.from_email or "?",
            submission_id,
            document_count,
        )

        return IntakeOutcome.QUEUED


async def record_failed_email(email: ParsedEmail | None, ref: str, reason: str) -> None:
    """The listener gave up on an email (it kept failing to be saved): keep a record
    with what is known (sender, subject, time) and state Failed, so a person sees it
    and can ask the sender to resend. Nothing from the email is read or queued."""
    async with SessionLocal() as session:
        submission = Submission(
            source=SubmissionSource.EMAIL,
            status=SubmissionStatus.FAILED,
            sender_email=((email.from_email if email else "") or "")[:255] or None,
            subject=((email.subject if email else "") or "")[:998] or None,
            message_id=email.message_id if email else f"<uid-{ref}@imap.local>",
            received_at=email.received_at if email else datetime.now(UTC),
            error="This email could not be saved and was skipped. Ask the sender to send "
            "it again; if that fails too, check the processing log.",
        )
        session.add(submission)
        await session.flush()
        set_state(session, submission, SubmissionState.RECEIVED, first=True)
        set_state(session, submission, SubmissionState.FAILED, reason=submission.error)
        record_step(
            session,
            submission_id=submission.id,
            step=StepName.COLLECT,
            result=StepResult.ERROR,
            message="The email could not be saved and was skipped.",
            input={"mailbox_ref": ref},
            error_details=reason,
        )
        await session.commit()


async def accept_email(email: ParsedEmail) -> str:
    """One session per email: a failure never leaves the next email in a broken session."""
    with pipeline_span("email.intake", attachments=len(email.attachments)) as span:
        async with SessionLocal() as session:
            outcome = await EmailIntakeService(session).accept(email)
        span.set_attribute("outcome", str(outcome))
        return outcome
