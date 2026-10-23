"""Bulk activate / deactivate (employees, companies, holidays) and bulk delete
(holidays). Each item is handled on its own: one failure never undoes the others."""

import uuid

from pydantic import BaseModel, Field, field_validator

MAX_BULK = 100  # one page of a list at most


def _unique(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(ids) != len(set(ids)):
        raise ValueError("Each id can appear only once.")
    return ids


class BulkIds(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)

    _check_ids = field_validator("ids")(_unique)


class BulkStatusRequest(BulkIds):
    is_active: bool


class BulkStatusItem(BaseModel):
    id: uuid.UUID
    ok: bool
    changed: bool = False  # false when it already had that status (or failed)
    is_active: bool | None = None  # the status afterwards (None = not found)
    error: str | None = None  # why it was skipped


class BulkStatusResult(BaseModel):
    requested: int
    succeeded: int
    failed: int
    results: list[BulkStatusItem]
    # Deactivating companies also deactivates their employees: how many.
    employees_deactivated: int = 0


class BulkDeleteResult(BaseModel):
    requested: int
    deleted: int
    failed: int
    results: list[BulkStatusItem]
