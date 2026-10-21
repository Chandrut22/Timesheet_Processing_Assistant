"""The optional attachment classifier, before any AI extraction call."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import StepName, StepResult
from src.core.services.activity_log import Stopwatch, current_reprocess_run, record_step
from src.core.services.attachment_classifier import (
    ClassifierError,
    ClassifierResult,
    Decision,
    decide,
    describe,
)
from src.data.clients.jev_client import classify
from src.data.models import Document, Submission
from src.observability.tracing.spans import pipeline_span


async def classified_as_not_timesheet(
    session: AsyncSession, submission: Submission, document: Document
) -> bool:
    """The optional attachment classifier (off by default). True = skip extraction.
    Every decision except "off" is written to the step log, so each skip can be checked."""
    if not settings.classifier_enabled:
        return False
    is_reprocess = current_reprocess_run.get() is not None
    result: ClassifierResult | None = None
    failure: str | None = None
    watch = Stopwatch()
    if not is_reprocess:
        with pipeline_span("ai.classify", model=settings.jev_model) as span:
            try:
                result = await classify(document.extracted_text or "")
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
    messages = {
        Decision.BYPASSED: "Classifier not used: a reprocess always runs the full extraction.",
        Decision.ERROR: "Classifier unavailable; extracted as usual.",
        Decision.CONTINUE: f"Classifier: {found}. Extracting.",
        Decision.SKIP: f"Not a timesheet (classifier: {found}). Not extracted.",
        Decision.SHADOW_SKIP: f"Shadow mode: would skip ({found}); extracting anyway.",
        Decision.SHADOW_CONTINUE: f"Shadow mode: {found}; would extract.",
    }
    record_step(
        session,
        submission_id=submission.id,
        document_id=document.id,
        step=StepName.CLASSIFY,
        result=StepResult.WARNING
        if decision in (Decision.SKIP, Decision.ERROR)
        else StepResult.SUCCESS,
        message=messages.get(decision, str(decision)),
        input={
            "characters_sent": min(
                len(document.extracted_text or ""), settings.classifier_max_chars
            )
        },
        output=output,
        error_details=failure,
        duration_ms=result.duration_ms if result else watch.ms,
    )
    if decision != Decision.SKIP:
        return False
    document.error = f"Not a timesheet (classifier: {found}). Reprocess to extract it anyway."
    return True
