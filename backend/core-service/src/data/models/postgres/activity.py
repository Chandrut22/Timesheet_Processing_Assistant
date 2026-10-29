"""The email state log and the step-by-step log. Both are append-only."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.timesheet_status import StepName, StepResult, SubmissionState
from src.data.models.postgres.base import SCHEMA, Base, UUIDPrimaryKeyMixin, enum_check


class SubmissionStateChange(UUIDPrimaryKeyMixin, Base):
    """One change of an email's / upload's state, with its time and reason."""

    __tablename__ = "submission_state_changes"
    __table_args__ = (
        enum_check("to_state", SubmissionState),
        Index("ix_submission_state_changes_submission", "submission_id", "created_at"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE")
    )
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    # auth-service user: UUID + name snapshot, no foreign key. Both None = the system.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_name: Mapped[str | None] = mapped_column(String(150))
    # clock_timestamp(), not now(): now() is the same for a whole transaction, and
    # several rows written in one transaction must keep their real order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class ProcessingStep(UUIDPrimaryKeyMixin, Base):
    """One step of the pipeline: what went in, what came out, how long, how it ended."""

    __tablename__ = "processing_steps"
    __table_args__ = (
        enum_check("step", StepName),
        enum_check("result", StepResult),
        Index("ix_processing_steps_submission", "submission_id", "created_at"),
        Index(
            "ix_processing_steps_document",
            "document_id",
            postgresql_where=text("document_id IS NOT NULL"),
        ),
        CheckConstraint("duration_ms >= 0", name="duration_non_negative"),
        Index(
            "ix_processing_steps_reprocess_run",
            "reprocess_run_id",
            postgresql_where=text("reprocess_run_id IS NOT NULL"),
        ),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.documents.id", ondelete="SET NULL")
    )
    timesheet_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid
    )  # plain: survives reprocessing
    # Set on every step written during a reprocess, so the timeline can group them by
    # run.
    reprocess_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.reprocess_runs.id", ondelete="SET NULL")
    )
    step: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)  # plain words for people
    input: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    error_details: Mapped[str | None] = mapped_column(
        Text
    )  # technical, for the log only
    duration_ms: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    # OpenTelemetry trace this step ran in (32 hex chars): the log records of that run
    # carry the same id.
    # NULL when tracing is off.
    trace_id: Mapped[str | None] = mapped_column(String(32))
    # clock_timestamp(), not now(): now() is the same for a whole transaction, and
    # several rows written in one transaction must keep their real order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
