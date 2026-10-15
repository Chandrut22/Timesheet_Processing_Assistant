import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from src.core.services.payroll_csv import (
    CSV_COLUMNS,
    ExportRow,
    build_csv,
    export_filename,
    safe_cell,
    totals,
    week_end,
)

WEEK = date(2026, 9, 14)


def row(
    code: str,
    name: str,
    regular: str = "40",
    overtime: str = "0",
    holiday: str = "0",
    approved_by: str | None = "Ravi Reviewer",
) -> ExportRow:
    return ExportRow(
        timesheet_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        employee_code=code,
        employee_name=name,
        regular=Decimal(regular),
        overtime=Decimal(overtime),
        double_time=Decimal("0"),
        holiday=Decimal(holiday),
        approved_by=approved_by,
        approved_at=datetime(2026, 9, 21, 10, 30, tzinfo=UTC),
    )


def parse(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_header_and_one_line_per_timesheet() -> None:
    text = build_csv("ABC Staffing", WEEK, [row("E2", "Priya Nair"), row("E1", "Rahul Kumar")])
    assert text.splitlines()[0].split(",") == CSV_COLUMNS
    lines = parse(text)
    assert [r["employee_code"] for r in lines] == ["E1", "E2"]  # sorted by code
    assert lines[0]["week_start"] == "2026-09-14"
    assert lines[0]["week_end"] == "2026-09-20"


def test_hours_have_two_decimals_and_total() -> None:
    lines = parse(build_csv("ABC", WEEK, [row("E1", "Mei Lin Chen", "32", "1.5", "8")]))
    assert lines[0]["regular_hours"] == "32.00"
    assert lines[0]["overtime_hours"] == "1.50"
    assert lines[0]["holiday_hours"] == "8.00"
    assert lines[0]["total_hours"] == "41.50"


def test_auto_approved_rows_are_labelled() -> None:
    lines = parse(build_csv("ABC", WEEK, [row("E1", "Priya Nair", approved_by=None)]))
    assert lines[0]["approved_by"] == "auto-approved"


def test_formula_like_text_is_neutralised() -> None:
    assert safe_cell('=HYPERLINK("x")') == '\'=HYPERLINK("x")'
    assert safe_cell("-5") == "'-5"
    assert safe_cell("Priya Nair") == "Priya Nair"
    lines = parse(build_csv("ABC", WEEK, [row("E1", "=cmd|' /C calc'!A0")]))
    assert lines[0]["employee_name"].startswith("'=")


def test_commas_and_quotes_in_names_stay_in_one_cell() -> None:
    lines = parse(build_csv('Smith, Jones & "Co"', WEEK, [row("E1", "O'Brien, Kate")]))
    assert lines[0]["company"] == 'Smith, Jones & "Co"'
    assert lines[0]["employee_name"] == "O'Brien, Kate"


def test_totals() -> None:
    t = totals([row("E1", "A", "40", "2"), row("E2", "B", "32", "0", "8")])
    assert t.rows == 2
    assert t.regular == Decimal("72")
    assert t.overtime == Decimal("2")
    assert t.holiday == Decimal("8")
    assert t.total == Decimal("82")


def test_empty_totals() -> None:
    t = totals([])
    assert t.rows == 0
    assert t.total == Decimal("0")


def test_filename_and_week_end() -> None:
    batch_id = uuid.UUID("1a2b3c4d-0000-0000-0000-000000000000")
    name = export_filename("ABC Staffing Solutions Pvt Ltd", WEEK, batch_id)
    assert name == "payroll_abc-staffing-solutions-pvt-ltd_2026-09-14_1a2b3c4d.csv"
    assert week_end(WEEK) == date(2026, 9, 20)
