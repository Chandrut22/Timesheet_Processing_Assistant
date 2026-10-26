"""Errors as JSON: every AppError becomes {"detail": ..., "code": ...} with its status,
and a database constraint refusal becomes a plain 409 (details in the log only)."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppError

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Every AppError becomes the same JSON shape: {"detail": ..., "code": ...}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
        headers=exc.headers,
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """A unique / check constraint said no (e.g. two requests creating the same email at
    once): 409 with a plain message instead of a 500. Details go to the log only."""
    logger.warning("Database refused a change on %s: %s", request.url.path, exc.orig)
    return JSONResponse(
        status_code=409,
        content={
            "detail": "This change conflicts with existing data. Reload and try again.",
            "code": "conflict",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
