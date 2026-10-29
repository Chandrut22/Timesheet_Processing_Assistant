"""Reprocessing history: who asked, when, why, and the results before and after.

Rows are never deleted. A reprocess updates the timesheets in place; what they were
before is kept in timesheet_versions (change "reprocessed")."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.timesheet_status import RefetchMode, ReprocessStatus
from src.data.models.postgres.base import SCHEMA, Base, UUIDPrimaryKeyMixin, enum_check


class ReprocessRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reprocess_runs"
    __table_args__ = (
        enum_check("status", ReprocessStatus),
        enum_check("refetch", RefetchMode),  # NULL passes: nothing fetched
        CheckConstraint("length(btrim(reason)) >= 3", name="reason_not_blank"),
        CheckConstraint(
            "(status = 'running') = (completed_at IS NULL)",
            name="completion_consistent",
        ),
        Index("ix_reprocess_runs_submission", "submission_id", "created_at"),
        Index(
            "ix_reprocess_runs_document",
            "document_id",
            postgresql_where=text("document_id IS NOT NULL"),
        ),
        # Only one reprocess at a time per submission.
        Index(
            "uq_reprocess_runs_one_running",
            "submission_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE")
    )
    # Set when only one attachment was reprocessed.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.documents.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text)
    # Fetch the email again from the mailbox first (RefetchMode), or NULL: use the saved
    # text.
    refetch: Mapped[str | None] = mapped_column(String(10))
    # auth-service user: UUID + name snapshot, no foreign key
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    requested_by_name: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(
        String(20), default=ReprocessStatus.RUNNING, server_default="running"
    )
    before_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    after_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
