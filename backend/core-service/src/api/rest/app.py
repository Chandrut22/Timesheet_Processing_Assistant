"""The FastAPI application: lifespan, middleware, routers and error handlers.

Middleware order: Starlette runs the LAST added first (outermost), so a request passes
CORS -> request log -> metrics -> auth -> rate limit -> routes. CORS is outermost, so a
401 or 429 still carries the CORS headers; the log and the metrics see every answer,
including the 401s and 429s of the inner middleware. The rate limit counts per client
IP (one limit for every endpoint, shared with auth-service)."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.cors import add_cors
from src.api.middleware.error_handler import register_exception_handlers
from src.api.middleware.logging import RequestLoggingMiddleware
from src.api.middleware.metrics import MetricsMiddleware
from src.api.middleware.rate_limit import Limit, RateLimitMiddleware
from src.api.rest.routes import (
    audit,
    companies,
    dashboard,
    email,
    employees,
    exports,
    health,
    holidays,
    me,
    sse,
    submissions,
    timesheets,
    uploads,
)
from src.config.settings import settings
from src.core.rbac.tokens import decode_access_token, public_key
from src.core.services.dashboard_hub import DashboardHub
from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import flush_logs
from src.observability.metrics.setup import setup_metrics, shutdown_metrics
from src.observability.tracing.setup import setup_tracing, shutdown_tracing

logger = logging.getLogger(__name__)
# Not logged or measured per request: health checks and the long-lived SSE stream.
NOT_MEASURED = (*settings.rate_limit_exempt_paths, "/dashboard/stream")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    public_key()  # fail fast at startup if the public key is missing
    hub = DashboardHub()
    await hub.start()
    app.state.dashboard_hub = hub
    logger.info("core-service started")

    yield

    await hub.stop()

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
    shutdown_metrics()
    shutdown_tracing()
    flush_logs()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    register_exception_handlers(app)
    # Tracing (only if OTEL_ENABLED): requests, SQL, Redis, and the queued Celery jobs.
    setup_tracing(app=app, engine=engine, celery=True)
    setup_metrics()  # only if OTEL_ENABLED and a collector endpoint is set

    app.add_middleware(
        RateLimitMiddleware,
        redis=redis_client,
        limit=Limit.parse(settings.rate_limit),
        enabled=settings.rate_limit_enabled,
        fail_open=settings.rate_limit_fail_open,
        exempt_paths=settings.rate_limit_exempt_paths,
    )
    app.add_middleware(
        AuthMiddleware,
        verify=decode_access_token,
        public_paths=settings.auth_public_paths,
        docs_enabled=settings.docs_enabled,
    )
    app.add_middleware(MetricsMiddleware, skip_paths=NOT_MEASURED)
    app.add_middleware(RequestLoggingMiddleware, skip_paths=NOT_MEASURED)
    add_cors(app)

    for routes in (
        health,
        me,
        companies,
        dashboard,
        sse,
        email,
        employees,
        holidays,
        uploads,
        submissions,
        timesheets,
        audit,
        exports,
    ):
        app.include_router(routes.router)
    return app
