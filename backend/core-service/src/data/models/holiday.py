import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.base import SCHEMA, Base, UUIDPrimaryKeyMixin


class Holiday(UUIDPrimaryKeyMixin, Base):
    """company_id NULL = a holiday for every company."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "holiday_date",
            name="uq_holidays_company_date",
            postgresql_nulls_not_distinct=True,
        ),
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="CASCADE"), index=True
    )
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(150))
    # An inactive holiday stays in the calendar but no longer counts in pay (from the
    # next calculation: timesheets already priced keep their pay until recalculated).
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
