from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, SmallInteger, String, text, true
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client company. Its pay rules are used by the rules engine."""

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("daily_ot_after > 0 AND daily_ot_after <= 24", name="daily_ot_after_range"),
        CheckConstraint(
            "weekly_ot_after > 0 AND weekly_ot_after <= 168", name="weekly_ot_after_range"
        ),
        CheckConstraint(
            "double_time_after IS NULL OR "
            "(double_time_after > daily_ot_after AND double_time_after <= 24)",
            name="double_time_after_range",
        ),
        CheckConstraint("week_start BETWEEN 0 AND 6", name="week_start_range"),
    )

    name: Mapped[str] = mapped_column(String(200), unique=True)
    # Hours are Numeric (exact), never float: payroll must not lose 0.01 h.
    daily_ot_after: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("8"), server_default=text("8")
    )
    weekly_ot_after: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("40"), server_default=text("40")
    )
    double_time_after: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # None = no rule
    week_start: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default=text("0")
    )  # 0 = Monday ... 6 = Sunday
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __repr__(self) -> str:
        return f"<Company {self.name}>"
