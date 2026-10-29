import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_COMPANIES = 500


def _required_company(value: uuid.UUID | None) -> uuid.UUID:
    if value is None:
        raise ValueError("Choose a company.")
    return value


class HolidayCreate(BaseModel):
    """A holiday belongs to ONE company (for several: POST /holidays/bulk/create)."""

    company_id: uuid.UUID | None = Field(
        default=None,
        validate_default=True,
        description="The company it applies to (required)",
    )
    holiday_date: date
    name: str = Field(min_length=1, max_length=150)

    _company = field_validator("company_id")(_required_company)


class HolidayBulkCreate(BaseModel):
    """The same holiday for several companies, in one go (all or nothing)."""

    company_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_COMPANIES)
    holiday_date: date
    name: str = Field(min_length=1, max_length=150)


class HolidayCopy(BaseModel):
    """Copy one company's holidays to other companies (a date they have already is
    skipped)."""

    from_company_id: uuid.UUID
    to_company_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_COMPANIES)
    year: int | None = Field(
        default=None, ge=2000, le=2100, description="Only this year"
    )


class HolidaySkipped(BaseModel):
    company_id: uuid.UUID
    holiday_date: date
    reason: str


class HolidayBulkResult(BaseModel):
    created: int
    skipped: list[HolidaySkipped]  # the company already had a holiday on that date


class HolidayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    holiday_date: date
    name: str
    is_active: bool  # false = kept in the calendar, but not counted in pay
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
