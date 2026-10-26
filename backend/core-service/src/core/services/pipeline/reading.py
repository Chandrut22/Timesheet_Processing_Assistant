"""Reading one file into text."""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import DocumentStatus, StepName, StepResult
from src.core.services.activity_log import Stopwatch, record_step
from src.core.services.documents.document_limits import DocumentTooLargeError
from src.core.services.documents.document_reader import (
    DocumentReadError,
    UnreadableFileError,
    read_document_full,
)
from src.data.clients import upload_buffer
from src.data.models import Document
from src.handlers.http_clients.vision_reader import VisionReadError
from src.utils.text import db_safe

logger = logging.getLogger(__name__)


def friendly_read_error(filename: str, exc: Exception) -> str:
    """A message a reviewer can act on; the technical text goes to error_details."""
    text = str(exc).lower()
    if "password" in text or "encrypt" in text:
        return f"'{filename}' is password-protected. Ask the sender for an unlocked copy."
    if "could not load document" in text or "conversion failed" in text:
        return f"'{filename}' is damaged or not a valid file. Ask the sender to resend it."
    return f"Could not read '{filename}'. Ask the sender to resend it."


def _from_vision(exc: BaseException) -> bool:
    """The vision reader could not open the image (its message is for people)."""
    return isinstance(exc.__cause__, VisionReadError)


async def read_document(session: AsyncSession, document: Document) -> None:
    watch = Stopwatch()
    step_input = {"file": document.filename, "size_bytes": document.size_bytes}
    data = await upload_buffer.get_file(document.id)
    if data is None:
        document.status = DocumentStatus.FAILED
        document.error = "The file expired before it was processed. Upload it again."
        record_step(
            session,
            submission_id=document.submission_id,
            document_id=document.id,
            step=StepName.READ,
            result=StepResult.ERROR,
            message=document.error,
            input=step_input,
            duration_ms=watch.ms,
        )
        return
    try:
        # Docling (or the vision model) is slow and blocking: run it off the event loop.
        # A vision model that cannot be reached raises VisionUnavailableError, which is
        # NOT caught here: the whole job fails as temporary and is retried later.
        outcome = await asyncio.to_thread(read_document_full, document.filename, data)
    except (DocumentReadError, DocumentTooLargeError) as exc:
        document.status = DocumentStatus.FAILED
        document.error = (
            str(exc)  # "has 120 pages; the limit is 50. Split it ..." / damaged / vision
            if isinstance(exc, (DocumentTooLargeError, UnreadableFileError)) or _from_vision(exc)
            else friendly_read_error(document.filename, exc)
        )
        record_step(
            session,
            submission_id=document.submission_id,
            document_id=document.id,
            step=StepName.READ,
            result=StepResult.ERROR,
            message=document.error,
            input=step_input,
            error_details=repr(exc),
            duration_ms=watch.ms,
        )
        logger.warning("Could not read %s: %s", document.filename, exc)
        return
    text, limit = outcome.text, outcome.limit
    document.extracted_text = text = db_safe(text)  # a NUL would make the save fail
    document.status = DocumentStatus.PARSED
    document.error = None
    stored_limit = limit.as_dict()
    document.read_limit = stored_limit or None
    document.read_method = outcome.method
    document.unclear_marks = outcome.unclear_marks
    document.writing_class = outcome.writing_class
    document.writing_confidence = (
        Decimal(str(round(outcome.writing_confidence, 2)))
        if outcome.writing_confidence is not None
        else None
    )
    document.has_handwritten_hours = outcome.has_handwritten_hours
    document.writing_reason = outcome.writing_reason
    vision = (
        {
            "model": outcome.model,
            "pages_read": outcome.pages_read,
            "writing_class": outcome.writing_class,
            "writing_confidence": outcome.writing_confidence,
            "has_handwritten_hours": outcome.has_handwritten_hours,
            "unclear_marks": outcome.unclear_marks,
        }
        if outcome.method == "vision"
        else {}
    )
    left_out = limit.content_left_out
    record_step(
        session,
        submission_id=document.submission_id,
        document_id=document.id,
        step=StepName.READ,
        result=StepResult.WARNING if left_out else StepResult.SUCCESS,
        message=f"Read {document.filename}"
        + (f" with the vision model ({outcome.writing_class})" if vision else "")
        + (" (too large: not every page / sheet was read)" if left_out else ""),
        input=step_input,
        # Counts and the class only: never the transcript, the reason or the images.
        output={
            "characters": len(text),
            "read_method": outcome.method,
            **vision,
            **stored_limit,
        },
        duration_ms=watch.ms,
    )
    logger.info("Read %s: %d characters", document.filename, len(text))
