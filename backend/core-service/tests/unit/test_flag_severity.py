from typing import Any

from src.constants.flags import Severity, highest_severity, severity_of, with_severity
from src.data.models import Timesheet
from src.schemas.timesheet import FlagRead


def test_use_case_severities() -> None:
    assert severity_of("long_day") is Severity.HIGH  # realistic hours
    assert severity_of("total_mismatch") is Severity.HIGH
    assert severity_of("duplicate_week") is Severity.HIGH  # duplicate
    assert severity_of("conflicting_hours") is Severity.HIGH
    assert severity_of("holiday_worked") is Severity.MEDIUM  # holiday pay
    assert severity_of("outside_assignment") is Severity.MEDIUM
    assert severity_of("dates_assumed") is Severity.LOW


def test_unknown_code_defaults_to_medium() -> None:
    assert severity_of("something_new") is Severity.MEDIUM
    assert severity_of(None) is Severity.MEDIUM


def test_with_severity_keeps_extra_keys_and_explicit_severity() -> None:
    flags: list[dict[str, Any]] = [
        {
            "code": "employee_unmatched",
            "message": "x",
            "candidates": [{"name": "Rahul Kumar"}],
        },
        {"code": "holiday_worked", "message": "y", "severity": "low"},
    ]
    result = with_severity(flags)
    assert result[0]["severity"] == "high"
    assert result[0]["candidates"] == [{"name": "Rahul Kumar"}]
    assert result[1]["severity"] == "low"  # an explicit value wins
    assert "severity" not in flags[0]  # the input is not changed


def test_highest_severity() -> None:
    assert highest_severity([]) is None
    assert (
        highest_severity([{"code": "dates_assumed"}, {"code": "holiday_worked"}])
        == "medium"
    )
    assert (
        highest_severity([{"code": "holiday_worked"}, {"code": "long_day"}]) == "high"
    )


def test_timesheet_fills_severity_whenever_flags_are_set() -> None:
    timesheet = Timesheet(flags=[{"code": "holiday_worked", "message": "Labor Day"}])
    assert timesheet.flags[0]["severity"] == "medium"
    assert timesheet.severity == "medium"

    timesheet.flags = [*timesheet.flags, {"code": "duplicate_week", "message": "again"}]
    assert timesheet.severity == "high"

    timesheet.flags = []
    assert timesheet.severity is None


def test_flag_read_passes_extra_keys_through() -> None:
    flag = FlagRead.model_validate(
        {
            "code": "duplicate_week",
            "message": "m",
            "severity": "high",
            "other_timesheet_id": "abc",
        }
    )
    assert flag.model_dump()["other_timesheet_id"] == "abc"
