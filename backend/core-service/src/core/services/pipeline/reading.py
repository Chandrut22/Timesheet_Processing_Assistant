"""Reading one file into text."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import DocumentStatus, StepName, StepResult
from src.core.services.activity_log import Stopwatch, record_step
from src.data.clients import upload_buffer
from src.data.clients.document_limits import DocumentTooLargeError
from src.data.clients.document_reader import DocumentReadError, read_document_with_limits
from src.data.models import Document
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
        # Docling is CPU-heavy and blocking: run it off the event loop.
        text, limit = await asyncio.to_thread(read_document_with_limits, document.filename, data)
    except (DocumentReadError, DocumentTooLargeError) as exc:
        document.status = DocumentStatus.FAILED
        document.error = (
            str(exc)  # "has 120 pages; the limit is 50. Split it ..."
            if isinstance(exc, DocumentTooLargeError)
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
    document.extracted_text = text = db_safe(text)  # a NUL would make the save fail
    document.status = DocumentStatus.PARSED
    document.error = None
    document.read_limit = limit.as_dict() or None
    left_out = limit.content_left_out
    record_step(
        session,
        submission_id=document.submission_id,
        document_id=document.id,
        step=StepName.READ,
        result=StepResult.WARNING if left_out else StepResult.SUCCESS,
        message=f"Read {document.filename}"
        + (" (too large: not every page / sheet was read)" if left_out else ""),
        input=step_input,
        output={"characters": len(text), **limit.as_dict()},
        duration_ms=watch.ms,
    )
    logger.info("Read %s: %d characters", document.filename, len(text))
