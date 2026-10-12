import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api.rest.dependencies import SessionDep
from src.api.rest.routes import auth, users
from src.config.settings import settings
from src.core.exceptions import AppError
from src.core.security import private_key, public_key
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.data.seed_data import run_seed

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


app = FastAPI(title=settings.app_name, lifespan=lifespan)
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}
