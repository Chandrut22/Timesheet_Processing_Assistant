"""Health checks for docker compose and load balancers (public, never rate-limited)."""

from fastapi import APIRouter
from sqlalchemy import text

from src.api.rest.dependencies import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}
