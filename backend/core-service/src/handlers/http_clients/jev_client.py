"""Jev (TypeSafe) client: classifies document text as timesheet / invoice / payslip /
other / unclear. Hosted API: https://api.typesafe.ai/v1/systemone (POST, Bearer key).

Request (as documented by TypeSafe's examples):
    {"model": "jev-1.13.0",
     "state": "<document text>",
     "questions": {"document_kind": {"type": "choice", "instructions": "...",
                                     "criteria": {"timesheet": "...", ...}}}}
The chosen label is answers.document_kind.choice. The exact field names for the
per-option probabilities were not published where we could see them, so
parse_response() accepts the likely shapes, and when it finds no probability for
"timesheet" it returns p_timesheet=None, which never skips a document.
CONFIRM THE RESPONSE FORMAT IN TYPESAFE'S DOCS before switching skipping on.

What is sent: the attachment's file name, the email subject and the start of the email
body (CLASSIFIER_BODY_MAX_CHARS), and the names of the other attachments (see
attachment_classifier.metadata_text). Never the file's contents, never the sender."""

import time
from typing import Any

import httpx

from src.config.settings import settings
from src.core.services.attachment_classifier import (
    LABELS,
    TIMESHEET,
    ClassifierError,
    ClassifierResult,
)

QUESTION = "document_kind"
INSTRUCTIONS = (
    "Classify one email attachment by its main purpose, judging only from its file "
    "name, the email subject and the email body (the file itself is not shown). The "
    "email was sent to a staffing company's payroll team, which pays hours from "
    "timesheets. Answer 'unclear' unless the name and the email make the purpose clear."
)


def build_request(text: str) -> dict[str, Any]:
    """Pure: the JSON body. At most CLASSIFIER_MAX_CHARS characters are sent."""
    return {
        "model": settings.jev_model,
        "state": text[: settings.classifier_max_chars],
        "questions": {
            QUESTION: {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": LABELS,
            }
        },
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 0 <= value <= 1 else None


def _timesheet_probability(answer: dict[str, Any], label: str) -> float | None:
    """P(timesheet) from the likely answer shapes, or None if not found."""
    for key in ("probabilities", "option_probabilities", "scores", "distribution"):
        table = answer.get(key)
        if isinstance(table, dict):  # {"timesheet": 0.93, "invoice": 0.04, ...}
            return _number(table.get(TIMESHEET))
        if isinstance(
            table, list
        ):  # [{"option": "timesheet", "probability": 0.93}, ...]
            for item in table:
                if not isinstance(item, dict):
                    continue
                name = item.get("option", item.get("label", item.get("choice")))
                if name == TIMESHEET:
                    return _number(
                        item.get("probability", item.get("p", item.get("score")))
                    )
    options = answer.get("options")
    if isinstance(options, list):
        for item in options:
            if (
                isinstance(item, dict)
                and item.get("option", item.get("label")) == TIMESHEET
            ):
                return _number(item.get("probability", item.get("p")))
    # Only a confidence for the chosen label: usable when the choice IS timesheet.
    if label == TIMESHEET:
        return _number(answer.get("confidence", answer.get("probability")))
    return None


def parse_response(data: Any, *, duration_ms: int = 0) -> ClassifierResult:
    """Pure: the API answer -> ClassifierResult. Raises ClassifierError if unusable."""
    try:
        answer = data["answers"][QUESTION]
        label = str(answer["choice"]).strip().lower()
    except (KeyError, TypeError) as exc:
        raise ClassifierError(
            f"Unexpected classifier answer: {str(data)[:200]}"
        ) from exc
    if label not in LABELS:
        raise ClassifierError(f"Unknown label from classifier: {label!r}")
    return ClassifierResult(
        label=label,
        p_timesheet=_timesheet_probability(answer, label),
        model=str(data.get("model") or settings.jev_model),
        duration_ms=duration_ms,
    )


async def classify(
    text: str, client: httpx.AsyncClient | None = None
) -> ClassifierResult:
    """Ask Jev. Raises ClassifierError on any problem (the caller then reads the file
    as usual)."""
    if settings.jev_api_key is None:
        raise ClassifierError("JEV_API_KEY is not set")
    if not text.strip():
        raise ClassifierError("No text to classify")
    headers = {"Authorization": f"Bearer {settings.jev_api_key.get_secret_value()}"}
    started = time.perf_counter()
    owned = client is None
    http = client or httpx.AsyncClient(timeout=settings.classifier_timeout_s)
    try:
        response = await http.post(
            settings.jev_url, json=build_request(text), headers=headers
        )
        response.raise_for_status()
        data = response.json()
    except (
        httpx.HTTPError,
        ValueError,
    ) as exc:  # timeout, connection, 4xx/5xx, not JSON
        raise ClassifierError(
            f"Classifier call failed: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if owned:
            await http.aclose()
    return parse_response(data, duration_ms=int((time.perf_counter() - started) * 1000))
