import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.base import SCHEMA, Base, UUIDPrimaryKeyMixin


class WhitelistSender(UUIDPrimaryKeyMixin, Base):
    """Who may send timesheets for a company: one exact email, or a whole domain.

    value is unique across ALL companies, so an incoming email always maps to
    exactly one company."""

    __tablename__ = "whitelist_senders"
    __table_args__ = (
        CheckConstraint("kind IN ('email', 'domain')", name="kind_valid"),
        CheckConstraint("value = lower(value)", name="value_lowercase"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))  # "email" | "domain"
    value: Mapped[str] = mapped_column(String(255), unique=True)  # "payroll@acme.com" | "acme.com"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
