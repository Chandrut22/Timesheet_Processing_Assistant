import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.config.settings import settings
from src.schemas.review import AuditEventRead
from src.utils.mail_link import mail_url
from src.utils.refetch import refetch_blocker


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    read_limit: dict[str, Any] | None  # pages / sheets not read (big files); None = all read
    read_method: str | None = None  # docling / plain / vision; None = not read yet
    unclear_marks: int = 0  # [UNCLEAR] left by the vision model (what it could not read)
    # Photos / scans: how they are written (None for typed documents, see WritingClass).
    writing_class: str | None = None
    writing_confidence: float | None = None
    has_handwritten_hours: bool = False
    writing_reason: str | None = None
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None


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
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    documents: list[DocumentRead]
    # Only used to build mail_url; not sent to the browser.
    message_id: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mail_url(self) -> str | None:
        """Opens this email in the mailbox (Gmail); None for uploads or when
        MAILBOX_ACCOUNT is not set."""
        return mail_url(
            self.source, self.message_id, settings.mailbox_account, settings.mailbox_link_template
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def refetch_blocked(self) -> str | None:
        """Why Reprocess cannot fetch this email again from the mailbox (None = it can)."""
        return refetch_blocker(
            self.source,
            self.message_id,
            enabled=settings.email_refetch_enabled,
            imap_ready=bool(settings.imap_host and settings.imap_user and settings.imap_password),
        )


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
    trace_id: str | None  # OpenTelemetry trace: search the logs by it; None when tracing is off
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
    refetch: bool | None = Field(
        default=None,
        description="Fetch the email again from the mailbox (by its Message-ID) and read "
        "the attachments again. Left out: only when needed (a file failed or expired, or the "
        "email was ignored). false: never; true: always (409 for uploads, or when "
        "fetching is not possible).",
    )
    confirm_approved: bool = Field(
        default=False,
        description="Needed when approved timesheets would be replaced: they go back to "
        "review (approvals are cleared). Without it the request is refused with 409 "
        "confirmation_required, listing them.",
    )


class ReprocessRunRead(BaseModel):
    """Who reprocessed, when, why, and the results before and after."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    document_id: uuid.UUID | None
    reason: str
    refetch: str | None  # missing | all: fetched again from the mailbox; None: saved text used
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
