import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.timesheet_status import DocumentStatus
from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check

if TYPE_CHECKING:
    from src.data.models.submission import Submission


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One attached file. The file itself is never stored: only its hash and,
    once read, its text."""

    __tablename__ = "documents"
    __table_args__ = (
        enum_check("status", DocumentStatus),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)  # same file twice -> duplicate
    status: Mapped[str] = mapped_column(
        String(20), default=DocumentStatus.PENDING, server_default="pending"
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    # What was NOT read of a big file (pages / sheets over the limit, empty or hidden
    # sheets), e.g. {"pages_total": 100, "pages_read": 50}. NULL = read in full.
    read_limit: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    submission: Mapped["Submission"] = relationship(back_populates="documents", lazy="raise")
