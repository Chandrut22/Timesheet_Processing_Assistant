import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = text("0")


class ExportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One payroll sheet: the approved timesheets of one client company for one week.

    The CSV is kept in the row, so the same file can be downloaded again later
    (no file storage). A week can have more than one batch: timesheets approved
    after the first export go into a second, smaller batch."""

    __tablename__ = "export_batches"
    __table_args__ = (Index("ix_export_batches_company_week", "company_id", "week_start"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT")
    )
    company_name: Mapped[str] = mapped_column(String(200))  # snapshot at export time
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)

    row_count: Mapped[int] = mapped_column(Integer)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)
    double_time_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)
    holiday_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=ZERO)

    filename: Mapped[str] = mapped_column(String(255))
    csv_content: Mapped[str] = mapped_column(Text)

    # auth-service user: UUID + name snapshot, no foreign key
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_by_name: Mapped[str | None] = mapped_column(String(150))

    def __repr__(self) -> str:
        return f"<ExportBatch {self.company_name} {self.week_start} rows={self.row_count}>"
