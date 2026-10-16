import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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


def _check_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise ValueError("assignment_end cannot be before assignment_start")


class EmployeeCreate(BaseModel):
    company_id: uuid.UUID
    employee_code: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    aliases: list[str] = Field(default_factory=list, max_length=20)
    assignment_start: date | None = Field(default=None, description="First day at the client")
    assignment_end: date | None = Field(default=None, description="Last day; null = ongoing")

    @model_validator(mode="after")
    def check_dates(self) -> "EmployeeCreate":
        _check_dates(self.assignment_start, self.assignment_end)
        return self

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
    assignment_start: date | None = None  # send null to clear
    assignment_end: date | None = None  # send null to clear (= ongoing)
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
    assignment_start: date | None
    assignment_end: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
