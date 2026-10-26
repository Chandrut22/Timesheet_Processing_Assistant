"""The FastAPI application: lifespan, middleware, routers and error handlers.

Middleware order: Starlette runs the LAST added first (outermost), so a request passes
CORS -> request log -> metrics -> auth -> rate limit -> routes. CORS is outermost, so a
401 or 429 still carries the CORS headers; the log and the metrics see every answer,
including the 401s and 429s of the inner middleware. The rate limit counts per client
IP (one limit for every endpoint, shared with core-service)."""

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
from src.api.rest.routes import auth, health, users
from src.config.settings import settings
from src.core.security import decode_access_token, private_key, public_key
from src.core.services.seed_service import run_seed
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import flush_logs
from src.observability.metrics.setup import setup_metrics, shutdown_metrics
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
    shutdown_metrics()
    shutdown_tracing()
    flush_logs()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        # Off unless DOCS_ENABLED=true: a deployed service does not publish its API map.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    setup_tracing(app=app, engine=engine)  # only if OTEL_ENABLED
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
    app.add_middleware(MetricsMiddleware, skip_paths=settings.rate_limit_exempt_paths)
    app.add_middleware(
        RequestLoggingMiddleware, skip_paths=settings.rate_limit_exempt_paths
    )
    add_cors(app)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    return app
