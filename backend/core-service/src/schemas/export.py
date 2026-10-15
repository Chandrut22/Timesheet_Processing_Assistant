import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.core.services.export_service import ExportPreviewResult
from src.core.services.payroll_csv import ExportRow, ExportTotals, week_end
from src.schemas.common import HoursOut


class ExportCreate(BaseModel):
    company_id: uuid.UUID
    week_start: date  # first day of the company's week
    allow_pending: bool = False  # export even if some timesheets still need review


class ExportRowRead(BaseModel):
    timesheet_id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    total_hours: HoursOut
    approved_by: str | None
    approved_at: datetime | None

    @classmethod
    def from_row(cls, row: ExportRow) -> "ExportRowRead":
        return cls(
            timesheet_id=row.timesheet_id,
            employee_id=row.employee_id,
            employee_code=row.employee_code,
            employee_name=row.employee_name,
            regular_hours=row.regular,
            overtime_hours=row.overtime,
            double_time_hours=row.double_time,
            holiday_hours=row.holiday,
            total_hours=row.total,
            approved_by=row.approved_by,
            approved_at=row.approved_at,
        )


class ExportTotalsRead(BaseModel):
    rows: int
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    total_hours: HoursOut

    @classmethod
    def from_totals(cls, t: ExportTotals) -> "ExportTotalsRead":
        return cls(
            rows=t.rows,
            regular_hours=t.regular,
            overtime_hours=t.overtime,
            double_time_hours=t.double_time,
            holiday_hours=t.holiday,
            total_hours=t.total,
        )


class ExportPreview(BaseModel):
    company_id: uuid.UUID
    company_name: str
    week_start: date
    week_end: date
    rows: list[ExportRowRead]
    totals: ExportTotalsRead
    pending_review: int  # still waiting for a reviewer (blocks the export by default)
    rejected: int  # never exported
    already_exported: int  # in an earlier payroll sheet for this week

    @classmethod
    def from_result(cls, r: ExportPreviewResult) -> "ExportPreview":
        return cls(
            company_id=r.company.id,
            company_name=r.company.name,
            week_start=r.week_start,
            week_end=week_end(r.week_start),
            rows=[ExportRowRead.from_row(row) for row in r.rows],
            totals=ExportTotalsRead.from_totals(r.totals),
            pending_review=r.pending_review,
            rejected=r.rejected,
            already_exported=r.already_exported,
        )


class ExportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    week_start: date
    week_end: date
    row_count: int
    regular_hours: HoursOut
    overtime_hours: HoursOut
    double_time_hours: HoursOut
    holiday_hours: HoursOut
    filename: str
    created_by_name: str | None
    created_at: datetime
