import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.read_methods import ReadMethod, WritingClass
from src.constants.timesheet_status import DocumentStatus
from src.data.models.postgres.base import (
    SCHEMA,
    AuditMixin,
    Base,
    UUIDPrimaryKeyMixin,
    enum_check,
)

if TYPE_CHECKING:
    from src.data.models.postgres.submission import Submission


class Document(UUIDPrimaryKeyMixin, AuditMixin, Base):
    """One attached file. The file itself is never stored: only its hash and,
    once read, its text."""

    __tablename__ = "documents"
    __table_args__ = (
        enum_check("status", DocumentStatus),
        enum_check(
            "read_method", ReadMethod
        ),  # NULL allowed: not read yet / older rows
        CheckConstraint("unclear_marks >= 0", name="unclear_marks_non_negative"),
        enum_check("writing_class", WritingClass),  # NULL: not read by the vision model
        CheckConstraint(
            "writing_confidence IS NULL OR (writing_confidence >= 0 AND "
            "writing_confidence <= 1)",
            name="writing_confidence_range",
        ),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(
        String(64), index=True
    )  # same file twice -> duplicate
    status: Mapped[str] = mapped_column(
        String(20), default=DocumentStatus.PENDING, server_default="pending"
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    # What was NOT read of a big file (pages / sheets over the limit, empty or hidden
    # sheets), e.g. {"pages_total": 100, "pages_read": 50}. NULL = read in full.
    read_limit: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # docling / plain / vision (ReadMethod); NULL until read (and for older rows).
    read_method: Mapped[str | None] = mapped_column(String(10))
    # How many [UNCLEAR] marks the vision model left in its transcription.
    unclear_marks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Photos / scans only (vision model): printed_only / handwritten_only / mixed /
    # no_text / uncertain, the lowest page confidence, handwritten hours anywhere, and a
    # short reason from visible evidence. NULL / false for typed documents.
    writing_class: Mapped[str | None] = mapped_column(String(20))
    writing_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    has_handwritten_hours: Mapped[bool] = mapped_column(
        default=False, server_default=false()
    )
    writing_reason: Mapped[str | None] = mapped_column(String(300))

    submission: Mapped["Submission"] = relationship(
        back_populates="documents", lazy="raise"
    )
