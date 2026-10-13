"""Short-lived buffer for uploaded files: the API puts the bytes here, the worker reads them.

This is NOT file storage: every key expires after UPLOAD_BUFFER_TTL_HOURS, and the
database only ever keeps the extracted text and the file's hash."""

import uuid

from redis.asyncio import Redis

from src.config.settings import settings
from src.data.clients.redis import redis_key

# Separate client WITHOUT decode_responses: the shared one turns values into str,
# which would corrupt PDFs and images.
_binary = Redis.from_url(settings.redis_url, decode_responses=False)


def _key(document_id: uuid.UUID) -> str:
    return redis_key("upload", str(document_id))


async def put_file(document_id: uuid.UUID, data: bytes) -> None:
    await _binary.set(_key(document_id), data, ex=settings.upload_buffer_ttl_hours * 3600)


async def get_file(document_id: uuid.UUID) -> bytes | None:
    value = await _binary.get(_key(document_id))
    return value if isinstance(value, bytes) else None


async def delete_file(document_id: uuid.UUID) -> None:
    await _binary.delete(_key(document_id))


async def close() -> None:
    await _binary.aclose()
