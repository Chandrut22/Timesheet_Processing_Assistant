"""Import every model here. Alembic only sees tables whose model was imported."""

from src.data.models.postgres.base import Base
from src.data.models.postgres.role import Role
from src.data.models.postgres.user import User

__all__ = ["Base", "Role", "User"]
