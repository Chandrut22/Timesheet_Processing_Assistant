import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.error_handlers import register_exception_handlers
from src.api.rest.routes import (
    audit,
    companies,
    employees,
    exports,
    health,
    holidays,
    me,
    submissions,
    timesheets,
    uploads,
)
from src.config.settings import settings
from src.core.rbac.tokens import public_key
from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import configure_logging
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    public_key()  # fail fast at startup if the public key is missing
    logger.info("core-service started")

    yield

    logger.info("Shutting down application resources...")
    try:
        await engine.dispose()
    except Exception:
        logger.exception("Error disposing the database engine")
    try:
        await redis_client.aclose()
    except Exception:
        logger.exception("Error closing the Redis client")

    try:
        await upload_buffer.close()
    except Exception:
        logger.exception("Error closing the upload buffer")
    shutdown_tracing()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
)
register_exception_handlers(app)
# Tracing (only if OTEL_ENABLED): requests, SQL, Redis, and the queued Celery jobs.
setup_tracing(app=app, engine=engine, celery=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],  # the payroll CSV's file name
)
app.include_router(health.router)
app.include_router(me.router)
app.include_router(companies.router)
app.include_router(employees.router)
app.include_router(holidays.router)
app.include_router(uploads.router)
app.include_router(submissions.router)
app.include_router(timesheets.router)
app.include_router(audit.router)
app.include_router(exports.router)
