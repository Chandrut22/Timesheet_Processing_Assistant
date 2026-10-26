import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.core.services.export_service import ExportPreviewResult
from src.core.services.payroll_csv import ExportRow, ExportTotals, week_end
from src.schemas.common import HoursOut, MoneyOut


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
    currency: str | None
    hourly_rate: MoneyOut | None
    overtime_rate: MoneyOut | None
    double_time_rate: MoneyOut | None
    holiday_rate: MoneyOut | None
    regular_amount: MoneyOut | None
    overtime_amount: MoneyOut | None
    double_time_amount: MoneyOut | None
    holiday_amount: MoneyOut | None
    gross_amount: MoneyOut | None  # None = not priced (blocks the export)
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
            currency=row.currency,
            hourly_rate=row.hourly_rate,
            overtime_rate=row.overtime_rate,
            double_time_rate=row.double_time_rate,
            holiday_rate=row.holiday_rate,
            regular_amount=row.regular_amount,
            overtime_amount=row.overtime_amount,
            double_time_amount=row.double_time_amount,
            holiday_amount=row.holiday_amount,
            gross_amount=row.gross,
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
    regular_amount: MoneyOut
    overtime_amount: MoneyOut
    double_time_amount: MoneyOut
    holiday_amount: MoneyOut
    gross_amount: MoneyOut
    unpriced: int  # rows without a pay amount; the export is refused while this is > 0

    @classmethod
    def from_totals(cls, t: ExportTotals) -> "ExportTotalsRead":
        return cls(
            rows=t.rows,
            regular_hours=t.regular,
            overtime_hours=t.overtime,
            double_time_hours=t.double_time,
            holiday_hours=t.holiday,
            total_hours=t.total,
            regular_amount=t.regular_amount,
            overtime_amount=t.overtime_amount,
            double_time_amount=t.double_time_amount,
            holiday_amount=t.holiday_amount,
            gross_amount=t.gross,
            unpriced=t.unpriced,
        )


class ExportPreview(BaseModel):
    company_id: uuid.UUID
    company_name: str
    week_start: date
    week_end: date
    currency: str
    rows: list[ExportRowRead]
    totals: ExportTotalsRead
    pending_review: int  # still waiting for a reviewer (blocks the export by default)
    rejected: int  # never exported
    already_exported: int  # in an earlier payroll sheet for this week
    problems: list[str]  # employees who would be paid twice (block the export)

    @classmethod
    def from_result(cls, r: ExportPreviewResult) -> "ExportPreview":
        return cls(
            company_id=r.company.id,
            company_name=r.company.name,
            week_start=r.week_start,
            week_end=week_end(r.week_start),
            currency=r.company.currency,
            rows=[ExportRowRead.from_row(row) for row in r.rows],
            totals=ExportTotalsRead.from_totals(r.totals),
            pending_review=r.pending_review,
            rejected=r.rejected,
            already_exported=r.already_exported,
            problems=r.problems,
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
    currency: str
    regular_amount: MoneyOut
    overtime_amount: MoneyOut
    double_time_amount: MoneyOut
    holiday_amount: MoneyOut
    gross_amount: MoneyOut
    filename: str
    created_by_name: str | None  # name of the user in created_by
    # Audit: when, and by which auth-service user (None = the system: a job or the
    # email listener). Filled by the database layer, never by the client.
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
