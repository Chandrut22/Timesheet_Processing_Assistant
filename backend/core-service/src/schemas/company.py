import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.schemas.common import HoursOut, MoneyOut

# Pay per hour: more than 0, at most 99,999,999.99, two decimals.
Rate = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
Alias = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


def _clean_aliases(values: list[str]) -> list[str]:
    """Drop duplicates (case-insensitive), keep the first spelling."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


class CompanyCreate(BaseModel):
    """Company A must set the pay rates when it creates a client company."""

    name: str = Field(min_length=1, max_length=200)
    aliases: list[Alias] = Field(
        default_factory=list, max_length=20, examples=[["ABC Staff."]]
    )
    hourly_rate: Rate = Field(description="Pay per regular hour", examples=["450.00"])
    overtime_rate: Rate = Field(
        description="Pay per overtime hour", examples=["675.00"]
    )
    double_time_rate: Rate | None = Field(
        default=None,
        description="Pay per double-time hour. Required with double_time_after.",
    )
    holiday_rate: Rate = Field(
        description="Pay per hour worked on a holiday", examples=["900.00"]
    )
    currency: Currency = "INR"
    daily_ot_after: Decimal = Field(default=Decimal("8"), gt=0, le=24, decimal_places=2)
    weekly_ot_after: Decimal = Field(
        default=Decimal("40"), gt=0, le=168, decimal_places=2
    )
    double_time_after: Decimal | None = Field(
        default=None, gt=0, le=24, decimal_places=2
    )
    week_start: int = Field(
        default=0, ge=0, le=6, description="0 = Monday ... 6 = Sunday"
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def unique_aliases(cls, value: list[str]) -> list[str]:
        return _clean_aliases(value)

    @model_validator(mode="after")
    def check_rules(self) -> "CompanyCreate":
        if (
            self.double_time_after is not None
            and self.double_time_after <= self.daily_ot_after
        ):
            raise ValueError("double_time_after must be greater than daily_ot_after")
        if self.double_time_after is not None and self.double_time_rate is None:
            raise ValueError(
                "double_time_rate is required when double_time_after is set"
            )
        return self


class CompanyUpdate(BaseModel):
    """Only the fields you send are changed. Send double_time_after: null to remove the
    rule. New rates apply to timesheets calculated afterwards; earlier ones keep their
    rates."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[Alias] | None = Field(default=None, max_length=20)
    hourly_rate: Rate | None = None
    overtime_rate: Rate | None = None
    double_time_rate: Rate | None = None
    holiday_rate: Rate | None = None
    currency: Currency | None = None
    daily_ot_after: Decimal | None = Field(default=None, gt=0, le=24, decimal_places=2)
    weekly_ot_after: Decimal | None = Field(
        default=None, gt=0, le=168, decimal_places=2
    )
    double_time_after: Decimal | None = Field(
        default=None, gt=0, le=24, decimal_places=2
    )
    week_start: int | None = Field(default=None, ge=0, le=6)
    is_active: bool | None = None

    @field_validator("aliases")
    @classmethod
    def unique_aliases(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_aliases(value)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    aliases: list[str]
    hourly_rate: MoneyOut
    overtime_rate: MoneyOut
    double_time_rate: MoneyOut | None
    holiday_rate: MoneyOut
    currency: str
    daily_ot_after: HoursOut
    weekly_ot_after: HoursOut
    double_time_after: HoursOut | None
    week_start: int
    is_active: bool
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None


class WhitelistCreate(BaseModel):
    value: str = Field(
        min_length=3, max_length=255, examples=["payroll@acme.com", "acme.com"]
    )


class WhitelistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    kind: str
    value: str
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
