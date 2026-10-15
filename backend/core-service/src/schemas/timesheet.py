import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.schemas.common import HoursOut


class TimesheetEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_date: date
    hours: HoursOut
    is_holiday: bool
    double_time_marked: bool
    note: str | None


class FlagRead(BaseModel):
    """One problem found on a timesheet. Extra keys (candidates, other_timesheet_id)
    are passed through as they are."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    severity: str  # high | medium | low


class TimesheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    document_id: uuid.UUID | None
    company_id: uuid.UUID | None
    employee_id: uuid.UUID | None
    extracted_name: str | None
    extracted_code: str | None
    week_start: date | None
    status: str
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    stated_total: HoursOut | None
    confidence: HoursOut | None
    match_method: str | None
    flags: list[FlagRead]
    severity: str | None  # worst flag severity, None = no flags
    notes: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    created_at: datetime
    entries: list[TimesheetEntryRead]
