import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.rest.dependencies import SessionDep
from src.api.rest.routes import auth, users
from src.config.settings import settings
from src.core.exceptions import AppError
from src.core.security import private_key, public_key
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.data.seed_data import run_seed
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    private_key()
    public_key()
    await run_seed()
    logger.info("auth-service started")

    yield

    logger.info("Shutting down application resources...")
    try:
        await engine.dispose()
        logger.info("Database connection pool disposed.")
    except Exception:
        logger.exception("Error disposing the database engine")

    try:
        await redis_client.aclose()
        logger.info("Redis connection pool closed.")
    except Exception:
        logger.exception("Error closing the Redis client")
    shutdown_tracing()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
setup_tracing(app=app, engine=engine)  # only if OTEL_ENABLED
# allow_credentials: the refresh token is an httpOnly cookie, so the frontend calls
# /auth/refresh and /auth/logout with credentials: "include".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(users.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Every AppError becomes the same JSON shape: {"detail": ..., "code": ...}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
        headers=exc.headers,
    )


@app.exception_handler(IntegrityError)
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}
