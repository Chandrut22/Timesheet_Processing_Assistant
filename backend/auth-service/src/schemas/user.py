import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.constants.roles import RoleName
from src.data.models import User

Password = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    """What the API shows about a user. Never includes password_hash."""

    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserRead":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role.name,  # Role is loaded with the user (lazy="selectin")
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Password
    role: RoleName

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class UserUpdate(BaseModel):
    """Every field optional: only what is sent is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    role: RoleName | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Password


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Password


class UserPage(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    size: int
