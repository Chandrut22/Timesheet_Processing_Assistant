import uuid

from pydantic import BaseModel

from src.constants.roles import RoleName


class PrincipalRead(BaseModel):
    id: uuid.UUID
    role: RoleName
    name: str
    email: str
