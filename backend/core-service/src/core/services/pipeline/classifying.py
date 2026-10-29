"""The optional attachment classifier, BEFORE any file is read.

It looks only at the email's metadata (each attachment's file name, the subject, the
body). An attachment it is sure is not a timesheet keeps the SKIPPED_BY_CLASSIFIER
message: it stays 'pending', so it is never read by Docling nor sent to the AI, and its
file stays in the buffer so a reprocess can read it. The email body (an email with no
readable attachment) is already 'parsed'; when skipped it is not sent to the AI. Uploads
from the screen and reprocess runs never use it."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    SKIPPED_BY_CLASSIFIER,
    DocumentStatus,
    StepName,
    StepResult,
    SubmissionSource,
)
from src.core.services.activity_log import Stopwatch, current_reprocess_run, record_step
from src.core.services.attachment_classifier import (
    ClassifierError,
    ClassifierResult,
    Decision,
    decide,
    describe,
    metadata_text,
)
from src.core.services.email_intake_service import BODY_FILENAME
from src.core.services.pipeline.finishing import already_extracted
from src.data.models import Document, Submission
from src.handlers.http_clients.jev_client import classify
from src.observability.tracing.spans import pipeline_span

__all__ = ["SKIPPED_BY_CLASSIFIER", "classify_by_metadata", "skipped_by_classifier"]

MESSAGES = {
    Decision.BYPASSED: "Classifier not used: a reprocess always reads the file and "
    "runs the full extraction.",
    Decision.ERROR: "Classifier unavailable; reading the file as usual.",
    Decision.CONTINUE: "Classifier: {found}. Reading the file.",
    Decision.SKIP: "Not a timesheet (classifier: {found}). Not read.",
    Decision.SHADOW_SKIP: "Shadow mode: would skip ({found}); reading anyway.",
    Decision.SHADOW_CONTINUE: "Shadow mode: {found}; would read.",
}


def skipped_by_classifier(document: Document) -> bool:
    """Left unread (or, for the email body, not extracted) on purpose by the
    classifier."""
    return (document.error or "").startswith(SKIPPED_BY_CLASSIFIER)


def waiting(document: Document) -> bool:
    """Not read yet, or the email body (saved as text on arrival)."""
    return document.status == DocumentStatus.PENDING or (
        document.status == DocumentStatus.PARSED and document.filename == BODY_FILENAME
    )


async def to_check(
    session: AsyncSession,
    submission: Submission,
    only_document: uuid.UUID | None,
    *,
    is_reprocess: bool,
) -> list[Document]:
    """The documents this run looks at. A reprocess also takes the ones the classifier
    skipped before (it reads them); a first run or a retry never asks again about one
    already skipped, nor about an email body already extracted."""
    found: list[Document] = []
    for d in submission.documents:
        if not waiting(d) or (only_document is not None and d.id != only_document):
            continue
        if not is_reprocess and skipped_by_classifier(d):
            continue
        if d.status == DocumentStatus.PARSED and await already_extracted(
            session, d.id, None
        ):
            continue
        found.append(d)
    return found


async def classify_by_metadata(
    session: AsyncSession, submission: Submission, only_document: uuid.UUID | None
) -> None:
    """Step 1, before reading: one classifier call per waiting email attachment (or
    the body, when the email has no readable attachment). Off by default. Every
    decision is written to the step log, so each skip can be checked."""
    if not settings.classifier_enabled or submission.source != SubmissionSource.EMAIL:
        return
    is_reprocess = current_reprocess_run.get() is not None
    names = [d.filename for d in submission.documents if d.filename != BODY_FILENAME]
    checked = await to_check(
        session, submission, only_document, is_reprocess=is_reprocess
    )
    for document in checked:
        is_body = document.filename == BODY_FILENAME
        others = [] if is_body else [n for n in names if n != document.filename]
        text = metadata_text(
            None if is_body else document.filename,
            submission.subject,
            submission.body_text,
            others,
            body_max=settings.classifier_body_max_chars,
        )
        await _classify_one(session, submission, document, text, is_reprocess)


async def _classify_one(
    session: AsyncSession,
    submission: Submission,
    document: Document,
    text: str,
    is_reprocess: bool,
) -> None:
    result: ClassifierResult | None = None
    failure: str | None = None
    watch = Stopwatch()
    if not is_reprocess:
        with pipeline_span("ai.classify", model=settings.jev_model) as span:
            try:
                result = await classify(text)
                span.set_attributes(
                    {"label": result.label, "p_timesheet": result.p_timesheet or -1.0}
                )
            except ClassifierError as exc:
                failure = str(exc)
                span.set_attribute("error", True)
    threshold = settings.classifier_skip_below
    decision = decide(
        result,
        enabled=True,
        shadow_only=settings.classifier_shadow_only,
        is_manual_reprocess=is_reprocess,
        threshold=threshold,
    )
    output: dict[str, Any] = {
        "decision": decision,
        "label": result.label if result else None,
        "p_timesheet": result.p_timesheet if result else None,
        "threshold": threshold,
        "model": result.model if result else settings.jev_model,
        "shadow_only": settings.classifier_shadow_only,
    }
    found = describe(result) if result else ""
    record_step(
        session,
        submission_id=submission.id,
        document_id=document.id,
        step=StepName.CLASSIFY,
        result=StepResult.WARNING
        if decision in (Decision.SKIP, Decision.ERROR)
        else StepResult.SUCCESS,
        message=MESSAGES.get(decision, str(decision)).format(found=found),
        input={"from": "metadata", "characters_sent": 0 if is_reprocess else len(text)},
        output=output,
        error_details=failure,
        duration_ms=result.duration_ms if result else watch.ms,
    )
    if decision == Decision.SKIP:
        document.error = (
            f"{SKIPPED_BY_CLASSIFIER} {found}, from the file name and the email). "
            "Reprocess to read it anyway."
        )
