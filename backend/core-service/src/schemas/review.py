import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EntryInput(BaseModel):
    work_date: date
    hours: Decimal = Field(ge=0, le=24, decimal_places=2)
    double_time_marked: bool = False
    is_holiday: bool = False
    note: str | None = Field(default=None, max_length=255)


class EntriesUpdate(BaseModel):
    """The full new list of days (replaces the old one)."""

    entries: list[EntryInput] = Field(max_length=31)

    @field_validator("entries")
    @classmethod
    def unique_dates(cls, value: list[EntryInput]) -> list[EntryInput]:
        dates = [e.work_date for e in value]
        if len(dates) != len(set(dates)):
            raise ValueError("Each date can appear only once.")
        return value


class MatchRequest(BaseModel):
    employee_id: uuid.UUID


class ApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


BULK_MAX = 100


def _unique_ids(value: list[uuid.UUID]) -> list[uuid.UUID]:
    """Drop repeated ids, keep the order."""
    return list(dict.fromkeys(value))


class BulkApproveRequest(BaseModel):
    timesheet_ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)
    notes: str | None = Field(default=None, max_length=1000)
    include_high_severity: bool = Field(
        default=False,
        description="Also approve timesheets with high-severity flags (off by default: "
        "those should be opened and approved one by one)",
    )

    @field_validator("timesheet_ids")
    @classmethod
    def unique_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class BulkRejectRequest(BaseModel):
    timesheet_ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("timesheet_ids")
    @classmethod
    def unique_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class BulkItemResult(BaseModel):
    timesheet_id: uuid.UUID
    ok: bool
    status: str | None = None  # the timesheet's status afterwards (None = not found)
    error: str | None = None  # why it was skipped


class BulkResult(BaseModel):
    """Each timesheet is handled on its own: one failure never undoes the others."""

    requested: int
    succeeded: int
    failed: int
    results: list[BulkItemResult]


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    details: dict[str, Any]
    created_at: datetime
