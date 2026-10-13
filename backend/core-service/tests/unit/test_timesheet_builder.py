import uuid
from datetime import date
from decimal import Decimal

from src.core.services.timesheet_builder import BuildContext, build_timesheet
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet

# Received on Wednesday 14 Oct 2026
CTX = BuildContext(
    submission_id=uuid.uuid4(),
    document_id=uuid.uuid4(),
    company_id=None,
    received_on=date(2026, 10, 14),
)


def codes(flags: list[dict[str, str]]) -> set[str]:
    return {f["code"] for f in flags}


def test_weekday_only_days_fall_back_to_previous_week_when_in_future() -> None:
    # Friday of the receipt week (16th) is in the future -> previous week (5th-9th)
    sheet = ExtractedTimesheet(
        employee_name="Bob",
        days=[ExtractedDay(weekday="Mon", hours=8), ExtractedDay(weekday="Fri", hours=8)],
        confidence=0.9,
    )
    ts = build_timesheet(sheet, CTX)
    assert [e.work_date for e in ts.entries] == [date(2026, 10, 5), date(2026, 10, 9)]
    assert ts.week_start == date(2026, 10, 5)
    assert "dates_assumed" in codes(ts.flags)


def test_total_mismatch_and_duplicate_day_are_flagged() -> None:
    sheet = ExtractedTimesheet(
        days=[
            ExtractedDay(work_date=date(2026, 10, 5), hours=4),
            ExtractedDay(work_date=date(2026, 10, 5), hours=4.5),
        ],
        stated_total=9,
        confidence=0.8,
    )
    ts = build_timesheet(sheet, CTX)
    assert len(ts.entries) == 1
    assert ts.entries[0].hours == Decimal("8.50")
    assert ts.regular_hours == Decimal("8.50")
    assert {"duplicate_day", "total_mismatch"} <= codes(ts.flags)


def test_no_hours_is_flagged() -> None:
    ts = build_timesheet(ExtractedTimesheet(confidence=0.2), CTX)
    assert ts.entries == []
    assert "no_entries" in codes(ts.flags)
