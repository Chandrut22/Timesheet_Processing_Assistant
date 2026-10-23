"""Reprocessing: which old timesheet a newly extracted one updates, and the summaries."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.constants.timesheet_status import SubmissionState
from src.core.services.activity_log import state_from_timesheets
from src.core.services.reprocess import pick_predecessor, snapshot, summarize
from src.data.models import Timesheet
from src.schemas.submission import ReprocessRequest

DOC_A = uuid.uuid4()
DOC_B = uuid.uuid4()
WEEK = date(2026, 10, 12)


def ts(
    name: str | None, doc: uuid.UUID = DOC_A, code: str | None = None, week: date | None = WEEK
) -> Timesheet:
    return Timesheet(
        id=uuid.uuid4(), document_id=doc, extracted_name=name, extracted_code=code, week_start=week
    )


def test_the_old_timesheet_is_found_by_name_in_the_same_document() -> None:
    olds = [ts("Priya"), ts("john "), ts("John", doc=DOC_B)]
    assert pick_predecessor(ts("John"), olds, only_one_new=False) is olds[1]


def test_the_same_name_in_two_weeks_goes_to_the_same_week() -> None:
    week2 = date(2026, 10, 19)
    olds = [ts("John"), ts("John", week=week2)]
    assert pick_predecessor(ts("John", week=week2), olds, only_one_new=False) is olds[1]


def test_falls_back_to_the_code() -> None:
    olds = [ts("John Mathew", code="syn-emp-020"), ts("Priya", code="SYN-EMP-002")]
    new = ts("J. Mathew", code="SYN-EMP-020")
    assert pick_predecessor(new, olds, only_one_new=False) is olds[0]


def test_one_old_and_one_new_go_together() -> None:
    only = ts("Rahul Kumar")
    assert pick_predecessor(ts("R. Kumar"), [only], only_one_new=True) is only
    assert pick_predecessor(ts("R. Kumar"), [only], only_one_new=False) is None


def test_none_when_ambiguous_or_missing() -> None:
    assert pick_predecessor(ts("Anna"), [ts("Bob"), ts("Carl")], only_one_new=True) is None
    assert pick_predecessor(ts("Anna"), [], only_one_new=True) is None


def test_the_email_state_comes_from_all_timesheets() -> None:
    assert state_from_timesheets([]) is None
    assert state_from_timesheets(["rejected", "approved"]) is SubmissionState.APPROVED
    assert state_from_timesheets(["rejected", "needs_review"]) is SubmissionState.AWAITING_REVIEW


def _timesheet(status: str, employee: bool) -> Timesheet:
    return Timesheet(
        id=uuid.uuid4(),
        version=1,
        extracted_name="John",
        status=status,
        employee_id=uuid.uuid4() if employee else None,
        regular_hours=Decimal(40),
        overtime_hours=Decimal(2),
        double_time_hours=Decimal(0),
        holiday_hours=Decimal(0),
        regular_amount=Decimal("18000"),
        overtime_amount=Decimal("1350"),
        double_time_amount=Decimal(0),
        holiday_amount=Decimal(0),
        flags=[{"code": "employee_unmatched", "message": "x"}] if not employee else [],
    )


def test_snapshot_counts_and_values() -> None:
    snap = snapshot(
        "awaiting_review", [_timesheet("needs_review", False), _timesheet("approved", True)]
    )
    assert snap["count"] == 2
    assert snap["unmatched"] == 1
    assert snap["needs_review"] == 1
    assert snap["approved"] == 1
    first = snap["timesheets"][0]
    assert first["total_hours"] == 42.0
    assert first["gross_amount"] == 19350.0
    assert first["flags"] == ["employee_unmatched"]


def test_summary_without_amounts_has_no_gross() -> None:
    timesheet = _timesheet("needs_review", False)
    timesheet.double_time_amount = None
    assert summarize(timesheet)["gross_amount"] is None


def test_a_reason_is_required() -> None:
    with pytest.raises(ValidationError):
        ReprocessRequest(reason="")
    with pytest.raises(ValidationError):
        ReprocessRequest(reason="ok")  # too short
    assert ReprocessRequest(reason="Employee list updated").document_id is None
