import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.rate_limit import Limit, RateLimitMiddleware
from src.api.rest.dependencies import SessionDep
from src.api.rest.routes import auth, users
from src.config.settings import settings
from src.core.exceptions import AppError
from src.core.security import decode_access_token, private_key, public_key
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


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    # Off unless DOCS_ENABLED=true: a deployed service does not publish its API map.
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
setup_tracing(app=app, engine=engine)  # only if OTEL_ENABLED
# allow_credentials: the refresh token is an httpOnly cookie, so the frontend calls
# /auth/refresh and /auth/logout with credentials: "include".
# Middleware order: Starlette runs the LAST added first (outermost), so requests pass
# CORS -> auth -> rate limit -> routes. CORS is outermost, so a 401 or 429 still carries
# the CORS headers the browser needs to read it; auth runs before the rate limit, so the
# limit can count per signed-in user.
app.add_middleware(
    RateLimitMiddleware,
    redis=redis_client,
    prefix="auth",
    limits={
        "strict": Limit.parse(settings.rate_limit_strict),
        "upload": Limit.parse(settings.rate_limit_upload),
        "default": Limit.parse(settings.rate_limit_default),
    },
    enabled=settings.rate_limit_enabled,
    fail_open=settings.rate_limit_fail_open,
    trusted_proxy_hops=settings.trusted_proxy_hops,
    exempt_paths=settings.rate_limit_exempt_paths,
    identify=lambda claims: (
        str(claims.get("sub")) if isinstance(claims, dict) else None
    ),
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
