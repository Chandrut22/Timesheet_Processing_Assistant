import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.schemas.common import HoursOut, MoneyOut


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
    extracted_company_name: str | None  # company as written on the sheet
    week_start: date | None
    status: str  # needs_review | approved | rejected | exported | superseded
    version: int  # 1 = first run, 2+ = after a reprocess
    reprocess_run_id: uuid.UUID | None  # the reprocess that produced this version
    superseded_by_id: uuid.UUID | None  # set on an old version: the one that replaced it
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    total_hours: HoursOut
    stated_total: HoursOut | None  # total written on the attachment
    email_stated_total: HoursOut | None  # total the email body gives (conflicting_hours check)
    # Gross pay (no taxes or deductions); rates are the ones used for this timesheet.
    # All None = not priced yet (no company, or a rate is missing: see the flags).
    currency: str | None
    hourly_rate: MoneyOut | None
    overtime_rate: MoneyOut | None
    double_time_rate: MoneyOut | None
    holiday_rate: MoneyOut | None
    regular_amount: MoneyOut | None
    overtime_amount: MoneyOut | None
    double_time_amount: MoneyOut | None
    holiday_amount: MoneyOut | None
    gross_amount: MoneyOut | None
    read_confidence: HoursOut | None  # how well the sheet was read (0-1)
    confidence: HoursOut | None  # overall: lower of reading and match confidence
    match_method: str | None
    match_reason: str | None  # e.g. "Matched Rahul Kumar (SYN-EMP-001) by initial + surname"
    flags: list[FlagRead]
    severity: str | None  # worst flag severity, None = no flags
    notes: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    created_at: datetime
    entries: list[TimesheetEntryRead]
