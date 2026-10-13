from fastapi import APIRouter
from sqlalchemy import text

from src.api.rest.dependencies import RedisDep, SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}


@router.get("/health/redis")
async def health_redis(redis: RedisDep) -> dict[str, str]:
    await redis.ping()
    return {"redis": "ok"}
