"""The payroll sheet itself: rows -> totals -> CSV text.

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

    @property
    def total(self) -> Decimal:
        return self.regular + self.overtime + self.double_time + self.holiday


@dataclass(frozen=True, slots=True)
class ExportTotals:
    rows: int
    regular: Decimal
    overtime: Decimal
    double_time: Decimal
    holiday: Decimal

    @property
    def total(self) -> Decimal:
        return self.regular + self.overtime + self.double_time + self.holiday


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def totals(rows: Sequence[ExportRow]) -> ExportTotals:
    return ExportTotals(
        rows=len(rows),
        regular=sum((r.regular for r in rows), ZERO),
        overtime=sum((r.overtime for r in rows), ZERO),
        double_time=sum((r.double_time for r in rows), ZERO),
        holiday=sum((r.holiday for r in rows), ZERO),
    )


def safe_cell(value: str) -> str:
    """Stop Excel from treating a name like '=HYPERLINK(...)' as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _hours(value: Decimal) -> str:
    return str(value.quantize(TWO_PLACES))


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