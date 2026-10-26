import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppError

logger = logging.getLogger(__name__)

# Constraint name (part) -> what to tell the person. Anything else gets the generic text.
CONSTRAINT_MESSAGES: dict[str, str] = {
    "uq_timesheet_entries_day": "Each date can appear only once on a timesheet.",
    "submissions_message_id": "This email was already received.",
    "uq_employees_company_code": "An employee with this code already exists in the company.",
    "uq_employees_company_email": "An employee with this email already exists in the company.",
    "uq_companies_name_lower": "A company with this name already exists.",
    "whitelist_senders": "This sender is already on a company's whitelist.",
    "holidays": "This holiday already exists for that date.",
    "reprocess_runs": "A reprocess of this email is already running.",
}
GENERIC_CONFLICT = (
    "This change conflicts with existing data (it may have been changed by someone else "
    "at the same time). Reload and try again."
)


def conflict_message(exc: IntegrityError) -> str:
    """Pure: a plain message for a constraint error, by the constraint's name."""
    orig = exc.orig
    name = str(
        getattr(orig, "constraint_name", None)
        or getattr(getattr(orig, "__cause__", None), "constraint_name", None)
        or ""
    )
    text = f"{name} {orig}".lower()
    for key, message in CONSTRAINT_MESSAGES.items():
        if key in text:
            return message
    return GENERIC_CONFLICT


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Every AppError becomes the same JSON shape: {"detail": ..., "code": ...}."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        """A unique / check / foreign-key constraint said no: 409 with a plain message
        instead of "Internal Server Error". The technical text goes to the log only."""
        logger.warning("Database refused a change on %s: %s", request.url.path, exc.orig)
        return JSONResponse(
            status_code=409, content={"detail": conflict_message(exc), "code": "conflict"}
        )
