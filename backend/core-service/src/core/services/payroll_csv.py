"""The payroll sheet itself: rows -> totals -> CSV text.

Hours by pay code, the rate used for each, the amount per pay code and the gross
amount. Gross pay only: no taxes or deductions.

Pure functions (no database), so the file format is unit-tested."""

import csv
import io
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")

CSV_COLUMNS = [
    "company",
    "week_start",
    "week_end",
    "employee_code",
    "employee_name",
    "regular_hours",
    "overtime_hours",
    "double_time_hours",
    "holiday_hours",
    "total_hours",
    "currency",
    "hourly_rate",
    "overtime_rate",
    "double_time_rate",
    "holiday_rate",
    "regular_amount",
    "overtime_amount",
    "double_time_amount",
    "holiday_amount",
    "gross_amount",
    "approved_by",
    "approved_at",
    "timesheet_id",
]

# A cell starting with one of these is run as a formula by Excel ("CSV injection").
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True, slots=True)
class ExportRow:
    timesheet_id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    regular: Decimal
    overtime: Decimal
    double_time: Decimal
    holiday: Decimal
    approved_by: str | None
    approved_at: datetime | None
    # Pay (copied from the timesheet). None = not priced; such rows block the export.
    currency: str | None = None
    hourly_rate: Decimal | None = None
    overtime_rate: Decimal | None = None
    double_time_rate: Decimal | None = None
    holiday_rate: Decimal | None = None
    regular_amount: Decimal | None = None
    overtime_amount: Decimal | None = None
    double_time_amount: Decimal | None = None
    holiday_amount: Decimal | None = None

    @property
    def total(self) -> Decimal:
        return self.regular + self.overtime + self.double_time + self.holiday

    @property
    def gross(self) -> Decimal | None:
        parts = (
            self.regular_amount,
            self.overtime_amount,
            self.double_time_amount,
            self.holiday_amount,
        )
        if any(p is None for p in parts):
            return None
        return sum((p for p in parts if p is not None), ZERO)

    @property
    def is_priced(self) -> bool:
        return self.gross is not None


@dataclass(frozen=True, slots=True)
class ExportTotals:
    rows: int
    regular: Decimal
    overtime: Decimal
    double_time: Decimal
    holiday: Decimal
    regular_amount: Decimal = ZERO
    overtime_amount: Decimal = ZERO
    double_time_amount: Decimal = ZERO
    holiday_amount: Decimal = ZERO
    unpriced: int = 0  # rows without a pay amount (not counted in the money totals)

    @property
    def total(self) -> Decimal:
        return self.regular + self.overtime + self.double_time + self.holiday

    @property
    def gross(self) -> Decimal:
        return (
            self.regular_amount
            + self.overtime_amount
            + self.double_time_amount
            + self.holiday_amount
        )


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def _sum(values: Sequence[Decimal | None]) -> Decimal:
    return sum((v for v in values if v is not None), ZERO)


def totals(rows: Sequence[ExportRow]) -> ExportTotals:
    priced = [r for r in rows if r.is_priced]
    return ExportTotals(
        rows=len(rows),
        regular=sum((r.regular for r in rows), ZERO),
        overtime=sum((r.overtime for r in rows), ZERO),
        double_time=sum((r.double_time for r in rows), ZERO),
        holiday=sum((r.holiday for r in rows), ZERO),
        regular_amount=_sum([r.regular_amount for r in priced]),
        overtime_amount=_sum([r.overtime_amount for r in priced]),
        double_time_amount=_sum([r.double_time_amount for r in priced]),
        holiday_amount=_sum([r.holiday_amount for r in priced]),
        unpriced=len(rows) - len(priced),
    )


def safe_cell(value: str) -> str:
    """Stop Excel from treating a name like '=HYPERLINK(...)' as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _hours(value: Decimal) -> str:
    return str(value.quantize(TWO_PLACES))


def _money(value: Decimal | None) -> str:
    return "" if value is None else str(value.quantize(TWO_PLACES))


def build_csv(company_name: str, week_start: date, rows: Sequence[ExportRow]) -> str:
    """One line per timesheet, sorted by employee code, then name."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in sorted(rows, key=lambda r: (r.employee_code, r.employee_name)):
        writer.writerow(
            [
                safe_cell(company_name),
                week_start.isoformat(),
                week_end(week_start).isoformat(),
                safe_cell(row.employee_code),
                safe_cell(row.employee_name),
                _hours(row.regular),
                _hours(row.overtime),
                _hours(row.double_time),
                _hours(row.holiday),
                _hours(row.total),
                row.currency or "",
                _money(row.hourly_rate),
                _money(row.overtime_rate),
                _money(row.double_time_rate),
                _money(row.holiday_rate),
                _money(row.regular_amount),
                _money(row.overtime_amount),
                _money(row.double_time_amount),
                _money(row.holiday_amount),
                _money(row.gross),
                safe_cell(row.approved_by or "auto-approved"),
                row.approved_at.isoformat(timespec="seconds") if row.approved_at else "",
                str(row.timesheet_id),
            ]
        )
    return buffer.getvalue()


def export_filename(company_name: str, week_start: date, batch_id: uuid.UUID) -> str:
    """payroll_abc-staffing-solutions-pvt-ltd_2026-09-14_1a2b3c4d.csv"""
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")[:60] or "company"
    return f"payroll_{slug}_{week_start.isoformat()}_{batch_id.hex[:8]}.csv"
