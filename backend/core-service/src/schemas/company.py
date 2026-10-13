import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.common import HoursOut


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    daily_ot_after: Decimal = Field(default=Decimal("8"), gt=0, le=24, decimal_places=2)
    weekly_ot_after: Decimal = Field(default=Decimal("40"), gt=0, le=168, decimal_places=2)
    double_time_after: Decimal | None = Field(default=None, gt=0, le=24, decimal_places=2)
    week_start: int = Field(default=0, ge=0, le=6, description="0 = Monday ... 6 = Sunday")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @model_validator(mode="after")
    def double_time_after_daily(self) -> "CompanyCreate":
        if self.double_time_after is not None and self.double_time_after <= self.daily_ot_after:
            raise ValueError("double_time_after must be greater than daily_ot_after")
        return self


class CompanyUpdate(BaseModel):
    """Only the fields you send are changed. Send double_time_after: null to remove the rule."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    daily_ot_after: Decimal | None = Field(default=None, gt=0, le=24, decimal_places=2)
    weekly_ot_after: Decimal | None = Field(default=None, gt=0, le=168, decimal_places=2)
    double_time_after: Decimal | None = Field(default=None, gt=0, le=24, decimal_places=2)
    week_start: int | None = Field(default=None, ge=0, le=6)
    is_active: bool | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    daily_ot_after: HoursOut
    weekly_ot_after: HoursOut
    double_time_after: HoursOut | None
    week_start: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WhitelistCreate(BaseModel):
    value: str = Field(min_length=3, max_length=255, examples=["payroll@acme.com", "acme.com"])


class WhitelistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    kind: str
    value: str
    created_at: datetime
