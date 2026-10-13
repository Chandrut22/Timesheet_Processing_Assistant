from datetime import date

from pydantic import BaseModel, Field


class ExtractedDay(BaseModel):
    work_date: date | None = Field(
        default=None,
        description="Date of this day (YYYY-MM-DD) if written on the sheet; otherwise null",
    )
    weekday: str | None = Field(default=None, description="Day name as written, e.g. 'Mon'")
    hours: float = Field(ge=0, le=24, description="Hours worked that day (7:30 -> 7.5)")
    double_time_marked: bool = Field(
        default=False,
        description="True only if the sheet explicitly marks these hours as double time",
    )
    note: str | None = Field(default=None, description="Short note for the day, e.g. 'holiday'")


class ExtractedTimesheet(BaseModel):
    employee_name: str | None = Field(default=None, description="Employee name exactly as written")
    employee_code: str | None = Field(default=None, description="Employee ID or code, if present")
    week_start: date | None = Field(
        default=None, description="First day of the period (YYYY-MM-DD) if written; otherwise null"
    )
    days: list[ExtractedDay] = Field(
        default_factory=list, description="One item per day that has hours"
    )
    stated_total: float | None = Field(
        default=None, description="Total hours written on the sheet, if any"
    )
    confidence: float = Field(ge=0, le=1, description="How sure you are the reading is correct")
    issues: list[str] = Field(
        default_factory=list, description="Anything unclear: illegible numbers, missing dates, ..."
    )


class ExtractionResult(BaseModel):
    timesheets: list[ExtractedTimesheet] = Field(
        default_factory=list,
        description="One item per person per week; empty if the document is not a timesheet",
    )
