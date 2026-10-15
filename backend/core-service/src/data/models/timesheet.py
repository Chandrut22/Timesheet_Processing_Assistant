import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.constants.flags import Severity, highest_severity, with_severity
from src.constants.timesheet_status import TimesheetStatus
from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check

if TYPE_CHECKING:
    from src.data.models.timesheet_entry import TimesheetEntry

ZERO = text("0")


class Timesheet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One person's week, extracted from a document."""

    __tablename__ = "timesheets"
    __table_args__ = (
        enum_check("status", TimesheetStatus),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        Index("ix_timesheets_employee_week", "employee_id", "week_start"),  # duplicate check
        enum_check("severity", Severity),
    )

    # Same service -> real foreign keys
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(  # None until matched
        Uuid, ForeignKey(f"{SCHEMA}.employees.id", ondelete="RESTRICT"), index=True
    )

    # What the document said (kept even after matching, for the reviewer)
    extracted_name: Mapped[str | None] = mapped_column(String(200))
    extracted_code: Mapped[str | None] = mapped_column(String(50))
    week_start: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(
        String(20), default=TimesheetStatus.NEEDS_REVIEW, server_default="needs_review", index=True
    )
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    double_time_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=0, server_default=ZERO
    )
    holiday_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    stated_total: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2)
    )  # total written on the sheet
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))  # 0.00 - 1.00
    match_method: Mapped[str | None] = mapped_column(String(30))  # code / email / name / alias ...
    # [{"code": "total_mismatch", "message": "Sheet says 42, entries add up to 40"}]
    flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # Other service (auth) -> UUID reference + name snapshot, NO foreign key
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewed_by_name: Mapped[str | None] = mapped_column(String(150))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entries: Mapped[list["TimesheetEntry"]] = relationship(
        back_populates="timesheet",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TimesheetEntry.work_date",
    )

    # Which payroll sheet it went into. Set once; a timesheet is never exported twice.
    export_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.export_batches.id", ondelete="RESTRICT"), index=True
    )

    # Worst flag severity (high / medium / low), None = no flags. Kept in step with
    # `flags` by _set_severity, so lists can filter and sort on it.
    severity: Mapped[str | None] = mapped_column(String(10), index=True)

    @validates("flags")
    def _set_severity(self, _key: str, flags: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Every time the flags are set: add each flag's severity and keep the worst one."""
        enriched = with_severity(flags or [])
        self.severity = highest_severity(enriched)
        return enriched
