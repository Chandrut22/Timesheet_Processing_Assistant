import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class HolidayCreate(BaseModel):
    company_id: uuid.UUID | None = Field(default=None, description="Leave empty for all companies")
    holiday_date: date
    name: str = Field(min_length=1, max_length=150)


class HolidayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    holiday_date: date
    name: str
    created_at: datetime
