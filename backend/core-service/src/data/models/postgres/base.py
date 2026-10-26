import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.data.actor import current_actor_id

# Every core-service table lives in this schema (core.companies, core.timesheets, ...).
# The database is shared with auth-service, which owns the "auth" schema.
SCHEMA = "core"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """id: UUID made by Python (app inserts) or Postgres (anything else)."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        sort_order=-100,  # keep id as the first column
    )


class AuditMixin:
    """When and by whom a row was created and last changed.

    created_by / updated_by are auth-service user UUIDs (no foreign key across
    services); NULL = the system (a Celery job, the email listener, the sweeper).
    They are filled by SQLAlchemy itself from data/actor.py: on INSERT both get the
    acting user, on every UPDATE (ORM saves and update() statements alike) updated_at
    and updated_by are set again, so no service has to remember to do it."""

    # Read the database's own values (now()) back with RETURNING on every INSERT and
    # UPDATE, so updated_at is never left expired (a lazy load would fail in async code).
    __mapper_args__ = {"eager_defaults": True}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=101
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, default=current_actor_id, sort_order=102
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, default=current_actor_id, onupdate=current_actor_id, sort_order=103
    )


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """CHECK (status IN ('received', 'processing', ...)) built from the Python enum,
    so the database and the code can never disagree about the allowed values."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")
