import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _clean_aliases(values: list[str]) -> list[str]:
    """Trim, drop blanks, drop case-insensitive duplicates, keep order."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        alias = " ".join(value.split())
        if alias and alias.lower() not in seen:
            seen.add(alias.lower())
            cleaned.append(alias)
    return cleaned


class EmployeeCreate(BaseModel):
    company_id: uuid.UUID
    employee_code: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    aliases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("employee_code", "full_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Cannot be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value: list[str]) -> list[str]:
        return _clean_aliases(value)


class EmployeeUpdate(BaseModel):
    """company_id cannot change: an employee's history belongs to one company."""

    employee_code: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    aliases: list[str] | None = Field(default=None, max_length=20)
    is_active: bool | None = None

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_aliases(value)


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    employee_code: str
    full_name: str
    email: str | None
    aliases: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
