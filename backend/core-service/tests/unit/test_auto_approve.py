import uuid
from datetime import date
from decimal import Decimal

from src.core.services.timesheet_validation import can_auto_approve
from src.data.models import Timesheet, TimesheetEntry


def sheet(**overrides: object) -> Timesheet:
    values: dict[str, object] = {
        "submission_id": uuid.uuid4(),
        "employee_id": uuid.uuid4(),
        "confidence": Decimal("0.95"),
        "flags": [],
        "entries": [TimesheetEntry(work_date=date(2026, 10, 5), hours=Decimal("8"))],
    }
    values.update(overrides)
    return Timesheet(**values)


def test_clean_sheet_is_auto_approved() -> None:
    assert can_auto_approve(sheet())


def test_unmatched_employee_needs_review() -> None:
    assert not can_auto_approve(sheet(employee_id=None))


def test_low_confidence_needs_review() -> None:
    assert not can_auto_approve(sheet(confidence=Decimal("0.70")))


def test_blocking_flag_needs_review() -> None:
    assert not can_auto_approve(
        sheet(flags=[{"code": "total_mismatch", "message": "x"}])
    )


def test_a_worked_holiday_goes_to_review() -> None:
    # Hours paid at the holiday rate are always checked by a person.
    assert not can_auto_approve(
        sheet(flags=[{"code": "holiday_worked", "message": "x"}])
    )
    assert not can_auto_approve(
        sheet(flags=[{"code": "holiday_in_week", "message": "x"}])
    )


def test_note_flags_do_not_block() -> None:
    assert can_auto_approve(
        sheet(flags=[{"code": "company_from_sheet", "message": "x"}])
    )


def test_no_entries_needs_review() -> None:
    assert not can_auto_approve(sheet(entries=[]))
