"""Reprocessing: old versions are kept, linked to the new ones, and never counted."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.constants.timesheet_status import SubmissionState
from src.core.services.activity_log import state_from_timesheets
from src.core.services.reprocess import pick_successor, snapshot, summarize
from src.data.models import Timesheet
from src.schemas.submission import ReprocessRequest

DOC_A = str(uuid.uuid4())
DOC_B = str(uuid.uuid4())


def item(name: str | None, doc: str = DOC_A, code: str | None = None) -> dict[str, object]:
    return {"id": str(uuid.uuid4()), "document_id": doc, "name": name, "code": code}


def test_successor_is_found_by_name_in_the_same_document() -> None:
    old = item("John")
    new = [item("Priya"), item("john "), item("John", doc=DOC_B)]
    assert pick_successor(old, new) == new[1]["id"]


def test_successor_falls_back_to_the_code() -> None:
    old = item("J. Mathew", code="SYN-EMP-020")
    new = [item("John Mathew", code="syn-emp-020"), item("Priya", code="SYN-EMP-002")]
    assert pick_successor(old, new) == new[0]["id"]


def test_successor_is_the_only_timesheet_of_the_document() -> None:
    assert pick_successor(item("R. Kumar"), [only := item("Rahul Kumar")]) == only["id"]


def test_no_successor_when_ambiguous_or_missing() -> None:
    assert pick_successor(item("Anna"), [item("Bob"), item("Carl")]) is None
    assert pick_successor(item("Anna"), []) is None


def test_superseded_timesheets_do_not_count_for_the_email_state() -> None:
    assert state_from_timesheets(["superseded"]) is None
    assert state_from_timesheets(["superseded", "approved"]) is SubmissionState.APPROVED
    assert state_from_timesheets(["superseded", "needs_review"]) is SubmissionState.AWAITING_REVIEW


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
