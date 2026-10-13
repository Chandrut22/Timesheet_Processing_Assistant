import uuid
from dataclasses import dataclass

from src.constants.roles import RoleName


@dataclass(frozen=True, slots=True)
class Principal:
    """The signed-in user, as stated by a verified auth-service token.

    id is the auth-service user UUID. Store it in core tables as a plain UUID
    column (no foreign key across services), next to a copy of the name."""

    id: uuid.UUID
    role: RoleName
    name: str
    email: str
