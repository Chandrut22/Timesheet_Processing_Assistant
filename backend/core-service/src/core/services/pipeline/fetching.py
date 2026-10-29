"""Fetching an email again from the mailbox, for a reprocess (reprocess_runs.refetch).

The database keeps each file's text and hash, not the file: its bytes are deleted once
read. So a file that failed or expired, or the attachments of an email that was ignored
when it arrived, can only be read again from the original email, which is usually still
in the mailbox. This step finds it by its Message-ID (read-only: no flag changes), puts
the attachments back in the upload buffer and sets their documents to pending, so the
read step reads them again.

It is the same submission, so the duplicate check (by Message-ID) never sees it as new
mail, and each attachment keeps its document id (matched by hash, then by name), so the
"same file seen before" check does not flag it against itself."""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from email.message import Message

from imap_tools.errors import MailboxLoginError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    DocumentStatus,
    RefetchMode,
    StepName,
    StepResult,
    SubmissionStatus,
)
from src.core.services.activity_log import Stopwatch, record_step
from src.core.services.email_intake_service import (
    BODY_FILENAME,
    IGNORED_NOT_READ,
    MIN_BODY_CHARS,
    body_document,
    document_for,
)
from src.core.services.failures import MailboxRefusedError, MailboxUnavailableError
from src.data.clients import upload_buffer
from src.data.models import Document, Submission
from src.handlers.email.imap_source import ImapSource, MailConnectionLostError
from src.handlers.email.parser import parse_message
from src.utils.refetch import refetch_blocker

logger = logging.getLogger(__name__)


def imap_ready() -> bool:
    return bool(settings.imap_host and settings.imap_user and settings.imap_password)


def blocker(submission: Submission) -> str | None:
    """Why this submission's email cannot be fetched again, or None."""
    return refetch_blocker(
        submission.source,
        submission.message_id,
        enabled=settings.email_refetch_enabled,
        imap_ready=imap_ready(),
    )


async def missing_file(document: Document) -> bool:
    """An attachment whose text is not saved and whose file is gone: only the original
    email can help. (A file skipped on purpose, e.g. a logo or a .zip, is not
    missing.)"""
    if document.filename == BODY_FILENAME:
        return False
    if document.status == DocumentStatus.FAILED or document.error == IGNORED_NOT_READ:
        return True
    if document.status == DocumentStatus.PENDING:
        return await upload_buffer.get_file(document.id) is None
    return False


async def needs_refetch(submission: Submission, documents: Sequence[Document]) -> bool:
    """Reprocessing these documents needs the original email (automatic refetch)."""
    if submission.status == SubmissionStatus.IGNORED:
        return True
    return any([await missing_file(d) for d in documents])


def _find(message_id: str) -> Message | None:
    with ImapSource() as source:
        return source.find_message(message_id, settings.imap_refetch_folders)


async def _fetch(message_id: str) -> Message | None:
    try:
        return await asyncio.to_thread(_find, message_id)
    except MailboxLoginError as exc:
        raise MailboxRefusedError("the login was refused") from exc
    except MailConnectionLostError as exc:
        raise MailboxUnavailableError(str(exc)) from exc


def _same_file(candidates: list[Document], fresh: Document) -> Document | None:
    """The existing document this attachment is: the same hash, else the same name."""
    same_hash = [d for d in candidates if d.sha256 == fresh.sha256]
    same_name = [d for d in candidates if d.filename == fresh.filename]
    found = same_hash or same_name
    return found[0] if found else None


def _to_read_again(document: Document, fresh: Document) -> None:
    """Back to 'pending' with the fetched file's facts; what the last read found is
    cleared."""
    document.filename = fresh.filename
    document.content_type = fresh.content_type
    document.size_bytes = fresh.size_bytes
    document.sha256 = fresh.sha256
    document.status = DocumentStatus.PENDING
    document.error = None
    document.extracted_text = None
    document.read_limit = None
    document.read_method = None
    document.unclear_marks = 0
    document.writing_class = None
    document.writing_confidence = None
    document.has_handwritten_hours = False
    document.writing_reason = None


def _give_up(documents: Sequence[Document], reason: str) -> None:
    """The file could not be fetched: a document without saved text fails with why.
    A document that was read before keeps its text (it is extracted from that)."""
    for document in documents:
        if document.status != DocumentStatus.PARSED:
            document.status = DocumentStatus.FAILED
            document.error = reason


async def refetch_from_mailbox(
    session: AsyncSession,
    submission: Submission,
    mode: RefetchMode,
    only_document: uuid.UUID | None,
) -> None:
    """Fetch the email again and put the wanted attachments back to be read. Raises
    MailboxUnavailableError (temporary: tried again later) or MailboxRefusedError."""
    watch = Stopwatch()
    scope = [
        d
        for d in submission.documents
        if d.filename != BODY_FILENAME
        and (only_document is None or d.id == only_document)
    ]
    wanted = (
        scope
        if mode == RefetchMode.ALL
        else [d for d in scope if await missing_file(d)]
    )
    step_input = {
        "mode": mode.value,
        "message_id": submission.message_id,
        "attachments": [d.filename for d in wanted],
    }

    def log(
        result: StepResult, message: str, output: dict[str, object] | None = None
    ) -> None:
        record_step(
            session,
            submission_id=submission.id,
            document_id=only_document,
            step=StepName.FETCH,
            result=result,
            message=message,
            input=step_input,
            output=output or {},
            duration_ms=watch.ms,
        )

    cannot = blocker(submission)
    if cannot is not None:
        _give_up(wanted, cannot)
        log(StepResult.ERROR, cannot)
        return

    message_id = submission.message_id or ""
    msg = await _fetch(message_id)
    folders = ", ".join(
        dict.fromkeys([settings.imap_folder, *settings.imap_refetch_folders])
    )
    if msg is None:
        reason = (
            f"The original email is no longer in the mailbox (searched {folders}): it "
            "may have been deleted or moved. Ask the sender to send it again."
        )
        _give_up(wanted, reason)
        log(StepResult.ERROR, reason)
        return

    email = parse_message(msg, fallback_id=message_id)
    if submission.sender_email and email.from_email != submission.sender_email:
        found_from = email.from_email or "an unknown sender"
        reason = (
            f"The email found in the mailbox is from {found_from}, not "
            f"{submission.sender_email}: it was not used. Ask the sender to send it "
            "again."
        )
        _give_up(wanted, reason)
        log(StepResult.ERROR, reason)
        return
    if settings.email_require_sender_auth and not email.sender_auth_passed:
        reason = "The sender could not be verified (SPF/DKIM/DMARC did not pass)."
        _give_up(wanted, reason)
        log(StepResult.ERROR, reason)
        return

    unmatched = list(scope)
    fetched: list[str] = []
    added: list[str] = []
    not_readable: list[dict[str, str | None]] = []
    for attachment in email.attachments[: settings.email_max_attachments]:
        fresh, readable = document_for(attachment)
        existing = _same_file(unmatched, fresh)
        if existing is not None:
            unmatched.remove(existing)
            if existing not in wanted:
                continue  # read fine before: its saved text is used
            target = existing
        elif only_document is None and not any(
            d.sha256 == fresh.sha256 for d in submission.documents
        ):
            fresh.id = uuid.uuid4()  # the file is stored under the id before the flush
            submission.documents.append(fresh)
            target = fresh
            added.append(fresh.filename)
        else:
            continue  # one attachment reprocess: leave the email's other files alone
        if readable:
            await upload_buffer.put_file(target.id, attachment.data)
            if target is not fresh:
                _to_read_again(target, fresh)
            fetched.append(target.filename)
        else:
            target.status = DocumentStatus.UNSUPPORTED
            target.error = fresh.error
            not_readable.append({"file": target.filename, "reason": fresh.error})

    gone = [d for d in wanted if d in unmatched]
    _give_up(gone, "This attachment is no longer in the email in the mailbox.")

    # An ignored email's text was not kept: keep it now, and read it when it is the
    # only possible timesheet (as on arrival).
    if submission.body_text is None and email.body_text:
        submission.body_text = email.body_text
    body = (email.body_text or "").strip()
    has_file = any(
        d.status in (DocumentStatus.PENDING, DocumentStatus.PARSED)
        for d in submission.documents
    )
    if only_document is None and not has_file and len(body) >= MIN_BODY_CHARS:
        submission.documents.append(body_document(body))
        added.append(BODY_FILENAME)

    output: dict[str, object] = {
        "fetched": fetched,
        "added": added,
        "not_readable": not_readable,
        "not_found": [d.filename for d in gone],
    }
    count = len(fetched) + (1 if BODY_FILENAME in added else 0)
    if count == 0:
        log(
            StepResult.WARNING,
            "Fetched the email again, but nothing in it could be read.",
            output,
        )
    else:
        log(
            StepResult.WARNING if gone or not_readable else StepResult.SUCCESS,
            f"Fetched again from the mailbox: {count} file(s) to read.",
            output,
        )
    logger.info(
        "Submission %s fetched again from the mailbox: %s", submission.id, output
    )
