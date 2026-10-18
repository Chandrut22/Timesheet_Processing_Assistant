import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.models.base import SCHEMA, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.data.models.timesheet import Timesheet


class TimesheetEntry(UUIDPrimaryKeyMixin, Base):
    """One day on a timesheet."""

    __tablename__ = "timesheet_entries"
    __table_args__ = (
        UniqueConstraint("timesheet_id", "work_date", name="uq_timesheet_entries_day"),
        CheckConstraint("hours >= 0 AND hours <= 24", name="hours_range"),
    )

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.timesheets.id", ondelete="CASCADE"), index=True
    )
    work_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Holiday in the end (marked on the sheet / by a reviewer, OR in the holiday
    # calendar). Recomputed by pay_rules.recalculate(); never edit it directly.
    is_holiday: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Marked as a holiday on the sheet itself, or by a reviewer. Kept apart from the
    # calendar so deleting a calendar holiday really removes it from the timesheet.
    sheet_holiday: Mapped[bool] = mapped_column(default=False, server_default=false())
    double_time_marked: Mapped[bool] = mapped_column(default=False, server_default=false())
    note: Mapped[str | None] = mapped_column(String(255))

    timesheet: Mapped["Timesheet"] = relationship(back_populates="entries", lazy="raise")
