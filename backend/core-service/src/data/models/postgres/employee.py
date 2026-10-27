import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.postgres.base import SCHEMA, AuditMixin, Base, UUIDPrimaryKeyMixin


class Employee(UUIDPrimaryKeyMixin, AuditMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        # Codes and emails are unique per company (two companies may both have "E001").
        UniqueConstraint("company_id", "employee_code", name="uq_employees_company_code"),
        UniqueConstraint("company_id", "email", name="uq_employees_company_email"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "assignment_end IS NULL OR assignment_start IS NULL "
            "OR assignment_end >= assignment_start",
            name="assignment_dates",
        ),
        # Close spellings (pg_trgm): see name_keys.
        Index(
            "ix_employees_name_keys_trgm",
            "name_keys",
            postgresql_using="gin",
            postgresql_ops={"name_keys": "gin_trgm_ops"},
        ),
    )

    # RESTRICT: a company with employees cannot be deleted (deactivate it instead).
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT"), index=True
    )
    employee_code: Mapped[str] = mapped_column(String(50))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    # Other names on timesheets: "Bob" for Robert, "Mohd" for Mohammed. Used by matching.
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), default=list, server_default=text("'{}'")
    )

    # Placement at the client: hours outside these dates are flagged (None = open-ended).
    assignment_start: Mapped[date | None] = mapped_column(Date)
    assignment_end: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Every name (full name + aliases) cleaned for fuzzy search: lowercase, no accents,
    # punctuation as spaces ("john smith bob"). Postgres computes it on every insert /
    # update (a generated column, see migration c4d8a2e6f0b3): never set it in code.
    name_keys: Mapped[str | None] = mapped_column(
        Text,
        Computed("core.employee_name_keys(full_name, aliases::text[])", persisted=True),
    )

    def __repr__(self) -> str:
        return f"<Employee {self.employee_code} {self.full_name}>"
