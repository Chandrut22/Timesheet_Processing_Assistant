from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.postgres.base import AuditMixin, Base, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, AuditMixin, Base):
    """A client company (Company B). Its pay rules and pay rates are used for every
    employee placed there. Company A sets the rates when it creates the company."""

    __tablename__ = "companies"
    __table_args__ = (
        # "ABC Staffing" and "abc staffing" are the same company.
        Index("uq_companies_name_lower", func.lower(text("name")), unique=True),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "hourly_rate > 0 AND overtime_rate > 0 AND holiday_rate > 0 AND "
            "(double_time_rate IS NULL OR double_time_rate > 0)",
            name="rates_positive",
        ),
        CheckConstraint(
            "double_time_after IS NULL OR double_time_rate IS NOT NULL",
            name="double_time_rate_required",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "daily_ot_after > 0 AND daily_ot_after <= 24", name="daily_ot_after_range"
        ),
        CheckConstraint(
            "weekly_ot_after > 0 AND weekly_ot_after <= 168",
            name="weekly_ot_after_range",
        ),
        CheckConstraint(
            "double_time_after IS NULL OR (double_time_after > daily_ot_after AND "
            "double_time_after <= 24)",
            name="double_time_after_range",
        ),
        CheckConstraint("week_start BETWEEN 0 AND 6", name="week_start_range"),
    )

    name: Mapped[str] = mapped_column(String(200))
    # Other spellings on timesheets: "ABC Staff." for "ABC Staffing Pvt Ltd".
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), default=list, server_default=text("'{}'")
    )

    # Pay per hour for each pay code. Money is Numeric (exact), never float.
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    overtime_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    double_time_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2)
    )  # needed with DT rule
    holiday_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), default="INR", server_default="INR")

    # Hours are Numeric (exact), never float: payroll must not lose 0.01 h.
    daily_ot_after: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("8"), server_default=text("8")
    )
    weekly_ot_after: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("40"), server_default=text("40")
    )
    double_time_after: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2)
    )  # None = no rule
    week_start: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default=text("0")
    )  # 0 = Monday ... 6 = Sunday
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __repr__(self) -> str:
        return f"<Company {self.name}>"
