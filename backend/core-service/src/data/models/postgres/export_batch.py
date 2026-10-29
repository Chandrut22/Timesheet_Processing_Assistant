import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.postgres.base import SCHEMA, AuditMixin, Base, UUIDPrimaryKeyMixin

ZERO = text("0")


class ExportBatch(UUIDPrimaryKeyMixin, AuditMixin, Base):
    """One payroll sheet: the approved timesheets of one client company for one week.

    The CSV is kept in the row, so the same file can be downloaded again later
    (no file storage). A week can have more than one batch: timesheets approved
    after the first export go into a second, smaller batch."""

    __tablename__ = "export_batches"
    __table_args__ = (
        Index("ix_export_batches_company_week", "company_id", "week_start"),
        CheckConstraint("week_end >= week_start", name="week_range"),
        CheckConstraint("row_count >= 0", name="row_count_non_negative"),
        CheckConstraint(
            "regular_hours >= 0 AND overtime_hours >= 0 AND double_time_hours >= 0 AND "
            "holiday_hours >= 0",
            name="hours_non_negative",
        ),
        CheckConstraint(
            "regular_amount >= 0 AND overtime_amount >= 0 AND double_time_amount >= 0 "
            "AND holiday_amount >= 0 AND gross_amount >= 0",
            name="amounts_non_negative",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT")
    )
    company_name: Mapped[str] = mapped_column(String(200))  # snapshot at export time
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)

    row_count: Mapped[int] = mapped_column(Integer)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)
    double_time_hours: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), server_default=ZERO
    )
    holiday_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)

    # Gross pay totals of the sheet (no taxes or deductions)
    currency: Mapped[str] = mapped_column(CHAR(3), default="INR", server_default="INR")
    regular_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=ZERO)
    overtime_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), server_default=ZERO
    )
    double_time_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), server_default=ZERO
    )
    holiday_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=ZERO)
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        Computed(
            "regular_amount + overtime_amount + double_time_amount + holiday_amount"
        ),
    )

    filename: Mapped[str] = mapped_column(String(255))
    csv_content: Mapped[str] = mapped_column(Text)

    # Name of the user in created_by (AuditMixin), kept for the export history list.
    created_by_name: Mapped[str | None] = mapped_column(String(150))

    def __repr__(self) -> str:
        return (
            f"<ExportBatch {self.company_name} {self.week_start} rows={self.row_count}>"
        )
