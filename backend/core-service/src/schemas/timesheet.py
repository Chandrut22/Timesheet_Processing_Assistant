import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.common import HoursOut, MoneyOut


class TimesheetEntryRead(BaseModel):
    """One day (stored in the timesheet's entries JSONB; a day is known by its date)."""

    model_config = ConfigDict(from_attributes=True)

    work_date: date
    hours: HoursOut
    is_holiday: bool  # holiday in the end (sheet / reviewer, or holiday calendar)
    sheet_holiday: bool  # marked by the sheet or a reviewer (send this back when editing)
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
    status: str  # needs_review | approved | rejected | exported
    version: int  # 1 when extracted; a new number per reprocess or "Create as new version";
    # a restore goes back to that version's number
    reprocess_run_id: uuid.UUID | None  # the last reprocess that changed it
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
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    entries: list[TimesheetEntryRead]


class TimesheetVersionSummary(BaseModel):
    """One version in the list: what it was and what changed it."""

    version: int
    current: bool  # the timesheet as it is now (after a restore, an earlier number)
    change: str | None  # what made the next version (None if nothing has yet)
    changed_by_name: str | None
    changed_at: datetime | None  # when the next version was made
    reason: str | None
    reprocess_run_id: uuid.UUID | None
    employee_id: uuid.UUID | None
    extracted_name: str | None
    week_start: date | None
    status: str | None  # its status at the time
    days: int
    total_hours: HoursOut
    gross_amount: MoneyOut | None
    flags: list[str]


class TimesheetVersionRead(TimesheetVersionSummary):
    """One version in full: the days and pay as they were."""

    entries: list[TimesheetEntryRead]
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    stated_total: HoursOut | None
    currency: str | None
    match_method: str | None
    match_reason: str | None
    notes: str | None


class RestoreRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
