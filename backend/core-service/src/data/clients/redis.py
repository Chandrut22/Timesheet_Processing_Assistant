from redis.asyncio import Redis

from src.config.settings import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def redis_key(*parts: str) -> str:
    """redis_key("job", "123") -> "core:job:123". Redis is shared, so always use this."""
    return ":".join((settings.redis_prefix, *parts))


async def get_redis() -> Redis:
    return redis_client
