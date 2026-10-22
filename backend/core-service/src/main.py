import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.error_handlers import register_exception_handlers
from src.api.middleware.rate_limit import Limit, RateLimitMiddleware
from src.api.rest.routes import (
    audit,
    companies,
    dashboard,
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
from src.core.rbac.principal import Principal
from src.core.rbac.tokens import decode_access_token, public_key
from src.data.clients import upload_buffer
from src.data.clients.postgres import engine
from src.data.clients.redis import redis_client
from src.observability.logging.setup import configure_logging
from src.observability.tracing.setup import setup_tracing, shutdown_tracing
from src.core.services.dashboard_hub import DashboardHub

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    public_key()  # fail fast at startup if the public key is missing
    hub = DashboardHub()
    await hub.start()
    app.state.dashboard_hub = hub
    logger.info("core-service started")
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
    shutdown_tracing()


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
# Middleware order: Starlette runs the LAST added first (outermost), so requests pass
# CORS -> auth -> rate limit -> routes. CORS is outermost, so a 401 or 429 still carries
# the CORS headers the browser needs to read it; auth runs before the rate limit, so the
# limit can count per signed-in user.
app.add_middleware(
    RateLimitMiddleware,
    redis=redis_client,
    prefix="core",
    limits={
        "upload": Limit.parse(settings.rate_limit_upload),
        "export": Limit.parse(settings.rate_limit_export),
        "default": Limit.parse(settings.rate_limit_default),
    },
    enabled=settings.rate_limit_enabled,
    fail_open=settings.rate_limit_fail_open,
    trusted_proxy_hops=settings.trusted_proxy_hops,
    exempt_paths=settings.rate_limit_exempt_paths,
    identify=lambda principal: str(principal.id) if isinstance(principal, Principal) else None,
)
app.add_middleware(
    AuthMiddleware,
    verify=decode_access_token,
    public_paths=settings.auth_public_paths,
    docs_enabled=settings.docs_enabled,
)
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
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(holidays.router)
app.include_router(uploads.router)
app.include_router(submissions.router)
app.include_router(timesheets.router)
app.include_router(audit.router)
app.include_router(exports.router)
