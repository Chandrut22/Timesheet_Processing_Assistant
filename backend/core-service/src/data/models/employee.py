import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, UniqueConstraint, Uuid, text, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
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

    def __repr__(self) -> str:
        return f"<Employee {self.employee_code} {self.full_name}>"
