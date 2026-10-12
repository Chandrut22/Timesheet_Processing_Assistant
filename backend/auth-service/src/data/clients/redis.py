from redis.asyncio import Redis

from src.config.settings import settings

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> Redis:
    """FastAPI dependency."""
    return redis_client
