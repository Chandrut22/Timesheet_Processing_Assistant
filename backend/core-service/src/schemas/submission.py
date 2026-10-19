import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.review import AuditEventRead


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    created_at: datetime


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    status: str
    state: str  # received ... exported, ignored, failed, reprocessing
    state_reason: str | None
    company_id: uuid.UUID | None
    sender_email: str | None
    subject: str | None
    uploaded_by_id: uuid.UUID | None
    uploaded_by_name: str | None
    received_at: datetime
    processed_at: datetime | None
    error: str | None  # plain message; technical details are in the processing log
    attempts: int  # runs of the current job (reset by a reprocess)
    retry_at: datetime | None  # next automatic run after a temporary failure
    documents: list[DocumentRead]


class StateChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_state: str | None
    to_state: str
    reason: str | None
    actor_name: str | None  # None = the system
    created_at: datetime


class ProcessingStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step: str
    result: str  # success | warning | error
    message: str
    document_id: uuid.UUID | None
    timesheet_id: uuid.UUID | None
    input: dict[str, Any]
    output: dict[str, Any]
    error_details: str | None
    duration_ms: int
    reprocess_run_id: uuid.UUID | None  # set on steps written during a reprocess
    trace_id: str | None  # OpenTelemetry trace (open in Jaeger); None when tracing is off
    created_at: datetime


class ReprocessRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=1000,
        examples=["Employee list updated: added John Mathew (SYN-EMP-020)"],
    )
    document_id: uuid.UUID | None = Field(
        default=None, description="Reprocess only this attachment (default: the whole email)"
    )


class ReprocessRunRead(BaseModel):
    """Who reprocessed, when, why, and the results before and after."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    document_id: uuid.UUID | None
    reason: str
    requested_by_name: str
    status: str  # running | completed | failed
    before_result: dict[str, Any]
    after_result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class SubmissionTimeline(BaseModel):
    """Everything that happened to one email or upload, oldest first."""

    submission: SubmissionRead
    states: list[StateChangeRead]
    steps: list[ProcessingStepRead]
    audit: list[AuditEventRead]  # reviewer and system decisions on its timesheets
    reprocess_runs: list[ReprocessRunRead]  # who reprocessed, when, why, before / after
