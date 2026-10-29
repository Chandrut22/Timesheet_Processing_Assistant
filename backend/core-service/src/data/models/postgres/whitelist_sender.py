import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.postgres.base import SCHEMA, AuditMixin, Base, UUIDPrimaryKeyMixin


class WhitelistSender(UUIDPrimaryKeyMixin, AuditMixin, Base):
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
    value: Mapped[str] = mapped_column(
        String(255), unique=True
    )  # "payroll@acme.com" | "acme.com"
