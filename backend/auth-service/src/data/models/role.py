import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.models.base import Base

if TYPE_CHECKING:  # only for type hints; avoids a circular import at runtime
    from src.data.models.user import User


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(30), unique=True)

    # lazy="raise": in async code a hidden lazy load would crash, so we make it
    # fail loudly instead. Load users explicitly when you need them.
    users: Mapped[list["User"]] = relationship(back_populates="role", lazy="raise")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
