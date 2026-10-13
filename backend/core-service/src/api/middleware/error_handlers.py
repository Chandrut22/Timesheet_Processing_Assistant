from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.exceptions import AppError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Every AppError becomes the same JSON shape: {"detail": ..., "code": ...}."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
            headers=exc.headers,
        )
