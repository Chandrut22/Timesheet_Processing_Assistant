"""Document text -> structured timesheets, using the LLM.

The prompt (system rules, the delimited untrusted blocks) is built in
extraction_prompt.py. Payroll maths (overtime, holidays) is NOT done here: the rules
engine does that."""

import logging
from datetime import datetime

from langchain_core.language_models import BaseChatModel

from src.config.settings import settings
from src.control.agents.extraction_prompt import SYSTEM_PROMPT, build_user_message
from src.control.agents.structured_output import (
    AnswerCutOffError,
    StructuredOutputError,
    invoke_structured,
)
from src.core.services.failures import AnswerTooLongError, explain
from src.handlers.http_clients.llm import get_chat_model, get_fallback_chat_model
from src.observability.tracing.spans import set_attributes
from src.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    pass


async def extract_timesheets(
    *,
    document_text: str,
    filename: str,
    received_at: datetime,
    email_subject: str | None = None,
    email_body: str | None = None,
    part: tuple[int, int] | None = None,
) -> ExtractionResult:
    """`part` = (n, of) when a long document was cut into overlapping pieces
    (chunking.py): this call sees only piece n, and the AI is told so."""
    user_message = build_user_message(
        document_text=document_text,
        filename=filename,
        received_at=received_at,
        email_subject=email_subject,
        email_body=email_body,
        part=part,
    )

    try:
        return await _ask(get_chat_model(), user_message)
    except AnswerCutOffError as exc:  # a different model will not make it fit
        raise AnswerTooLongError(str(exc)) from exc
    except (
        Exception
    ) as exc:  # no valid JSON, or an API error: provider down, bad key ...
        main_error = exc

    fallback = get_fallback_chat_model()
    if fallback is None:
        raise _as_extraction_error(main_error) from main_error

    # The main model could not answer: ask the fallback model, with its own fresh
    # retries. Only the model names and the kind of error are logged, never the
    # document.
    logger.warning(
        "Main LLM %s failed (%s); asking the fallback model %s",
        settings.llm_model,
        type(main_error).__name__,
        settings.llm_fallback_model,
    )
    set_attributes(
        model=settings.llm_fallback_model,
        llm_fallback_used=True,
        llm_main_error=type(main_error).__name__,
    )
    try:
        return await _ask(fallback, user_message)
    except AnswerCutOffError as exc:
        raise AnswerTooLongError(str(exc)) from exc
    except Exception as fallback_error:
        # Both failed. Report the main model's failure when that was temporary (an
        # outage: the job is retried later); otherwise the fallback's.
        cause = main_error if explain(main_error).temporary else fallback_error
        error = ExtractionError(
            f"The main model failed ({_one_line(main_error)}) and so did the fallback "
            f"model ({_one_line(fallback_error)})."
        )
        raise error from cause


async def _ask(model: BaseChatModel, user_message: str) -> ExtractionResult:
    return await invoke_structured(
        model,
        ExtractionResult,
        system=SYSTEM_PROMPT,
        user=user_message,
        retries=settings.llm_json_retries,
    )


def _as_extraction_error(exc: Exception) -> ExtractionError:
    if isinstance(exc, StructuredOutputError):
        return ExtractionError(str(exc))
    return ExtractionError(
        f"The LLM call failed: {exc}"
    )  # bad key, unknown model, provider down


def _one_line(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160] if str(exc) else ''}"
