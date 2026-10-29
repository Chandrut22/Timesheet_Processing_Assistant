import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.postgres.base import SCHEMA, AuditMixin, Base, UUIDPrimaryKeyMixin


class Holiday(UUIDPrimaryKeyMixin, AuditMixin, Base):
    """A holiday of ONE company: hours worked on it are paid at that company's holiday
    rate. A holiday for several companies is one row per company (bulk create /
    copy)."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("company_id", "holiday_date", name="uq_holidays_company_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="CASCADE"), index=True
    )
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(150))
    # An inactive holiday stays in the calendar but no longer counts in pay (from the
    # next calculation: timesheets already priced keep their pay until recalculated).
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
