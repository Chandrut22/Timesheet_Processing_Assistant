"""Document text -> structured timesheets, using the LLM.

The prompt (system rules, the delimited untrusted blocks) is built in
extraction_prompt.py. Payroll maths (overtime, holidays) is NOT done here: the rules
engine does that."""

from datetime import datetime

from src.config.settings import settings
from src.control.agents.extraction_prompt import SYSTEM_PROMPT, build_user_message
from src.control.agents.structured_output import (
    AnswerCutOffError,
    StructuredOutputError,
    invoke_structured,
)
from src.core.services.failures import AnswerTooLongError
from src.data.clients.llm import get_chat_model
from src.schemas.extraction import ExtractionResult


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
    """`part` = (n, of) when a big sheet was cut into pieces (chunking.py): this call
    sees only piece n, and the AI is told so."""
    user_message = build_user_message(
        document_text=document_text,
        filename=filename,
        received_at=received_at,
        email_subject=email_subject,
        email_body=email_body,
        part=part,
    )

    try:
        return await invoke_structured(
            get_chat_model(),
            ExtractionResult,
            system=SYSTEM_PROMPT,
            user=user_message,
            retries=settings.llm_json_retries,
        )
    except AnswerCutOffError as exc:
        raise AnswerTooLongError(str(exc)) from exc
    except StructuredOutputError as exc:
        raise ExtractionError(str(exc)) from exc
    except Exception as exc:  # API errors: bad key, unknown model, provider down
        raise ExtractionError(f"The LLM call failed: {exc}") from exc
