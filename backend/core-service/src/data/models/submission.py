import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.timesheet_status import SubmissionSource, SubmissionState, SubmissionStatus
from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check

if TYPE_CHECKING:
    from src.data.models.document import Document


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One email or one upload. Holds one or more documents."""

    __tablename__ = "submissions"
    __table_args__ = (
        enum_check("source", SubmissionSource),
        enum_check("status", SubmissionStatus),
        enum_check("state", SubmissionState),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("(retry_at IS NULL) = (retry_token IS NULL)", name="retry_fields_together"),
        CheckConstraint(
            "status <> 'processed' OR processed_at IS NOT NULL", name="processed_has_time"
        ),
    )

    source: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(
        String(20), default=SubmissionStatus.RECEIVED, server_default="received", index=True
    )
    # What people see (received ... exported, ignored, failed). `status` above is the
    # worker's own bookkeeping; every state change is logged in submission_state_changes.
    state: Mapped[str] = mapped_column(
        String(20), default=SubmissionState.RECEIVED, server_default="received", index=True
    )
    state_reason: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT"), index=True
    )

    # Email submissions (filled by the email listener next week)
    sender_email: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(
        String(998), unique=True
    )  # stops double-processing

    # Upload submissions. auth-service user = UUID reference + name snapshot, NO foreign key.
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    uploaded_by_name: Mapped[str | None] = mapped_column(String(150))

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,  # review-list sort
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)  # plain message for people; details in steps
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="submission",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Document.filename",
    )
