"""Short-lived store for uploaded and emailed files: the API / email listener puts the
bytes here, the worker reads them and then deletes them.

Files live on disk under UPLOAD_DIR (in Docker: the shared volume "uploads", mounted in
core-service, core-worker and core-email), one file per document: <document id>.bin.
They are NOT kept in Redis, so a backlog of big files can never fill Redis's memory and
take the job queue down with it.

This is still NOT file storage: the database only keeps the extracted text and the
file's hash, the worker deletes a file once its text is saved, and the sweeper deletes
anything older than UPLOAD_BUFFER_TTL_HOURS (a file nobody read)."""

import asyncio
import os
import time
import uuid
from pathlib import Path

from src.config.settings import settings

SUFFIX = ".bin"


def _root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path(document_id: uuid.UUID) -> Path:
    return _root() / f"{document_id}{SUFFIX}"  # a UUID: no user text in the path


def _ttl_seconds() -> int:
    return settings.upload_buffer_ttl_hours * 3600


def _write(document_id: uuid.UUID, data: bytes) -> None:
    final = _path(document_id)
    temp = final.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with open(temp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, final)  # atomic: a reader never sees half a file


def _read(document_id: uuid.UUID) -> bytes | None:
    path = _path(document_id)
    try:
        if time.time() - path.stat().st_mtime > _ttl_seconds():
            path.unlink(missing_ok=True)  # expired, as the Redis key used to
            return None
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _purge(older_than_seconds: int) -> int:
    cutoff = time.time() - older_than_seconds
    removed = 0
    for path in _root().iterdir():
        if path.suffix not in (SUFFIX, ".tmp"):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


async def put_file(document_id: uuid.UUID, data: bytes) -> None:
    await asyncio.to_thread(_write, document_id, data)


async def get_file(document_id: uuid.UUID) -> bytes | None:
    return await asyncio.to_thread(_read, document_id)


async def delete_file(document_id: uuid.UUID) -> None:
    await asyncio.to_thread(lambda: _path(document_id).unlink(missing_ok=True))


async def purge_expired() -> int:
    """Delete files older than UPLOAD_BUFFER_TTL_HOURS. Returns how many."""
    return await asyncio.to_thread(_purge, _ttl_seconds())


async def close() -> None:
    """Nothing to close (kept so callers need no change)."""
    return None
