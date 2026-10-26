import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.actor import current_actor_id
from src.data.models.postgres.base import SCHEMA, Base

if TYPE_CHECKING:
    from src.data.models.postgres.role import Role


class User(Base):
    __tablename__ = "users"
    # Read now() back with RETURNING on INSERT and UPDATE, so updated_at is never left
    # expired after a save (a lazy load would fail in async code).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 (SQLAlchemy reads it)
    __table_args__ = (
        # The database itself refuses "Admin@X.com"; the app must lowercase first.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.roles.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Who created / last changed this user (NULL = the system, e.g. the seed script).
    # Filled from data/actor.py on every INSERT and UPDATE.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        default=current_actor_id,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
        default=current_actor_id,
        onupdate=current_actor_id,
    )

    # selectin: the role is loaded together with the user (one extra query),
    # so user.role works in async code without a lazy load.
    role: Mapped["Role"] = relationship(back_populates="users", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
