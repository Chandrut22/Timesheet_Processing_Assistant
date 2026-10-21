"""A sheet that gives only a weekly total per person ("Chandru - 40 h", no days)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.constants.flags import FLAG_SEVERITY, Severity
from src.control.agents.extraction_prompt import SYSTEM_PROMPT
from src.core.services.pay_rules import (
    PayRules,
    apply_weekly_total,
    has_hours,
    recalculate,
    weekly_total,
)
from src.core.services.timesheet_builder import BuildContext, build_timesheets
from src.core.services.timesheet_validation import can_auto_approve
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet

# The email arrived on Tuesday 20 Oct 2026; weeks start on Monday.
CTX = BuildContext(
    submission_id=uuid.uuid4(),
    document_id=uuid.uuid4(),
    company_id=None,
    received_on=date(2026, 10, 20),
)
RULES = PayRules(
    hourly_rate=Decimal("450"),
    overtime_rate=Decimal("675"),
    double_time_rate=Decimal("900"),
    holiday_rate=Decimal("900"),
    currency="INR",
)


def codes(flags: list[dict[str, str]] | None) -> list[str]:
    return [f["code"] for f in flags or []]


def total_only(name: str, hours: float, **extra: object) -> ExtractedTimesheet:
    return ExtractedTimesheet(
        employee_name=name,
        days=[],
        stated_total=hours,
        confidence=0.95,
        **extra,
    )


@pytest.mark.parametrize(
    ("name", "hours", "regular", "overtime", "gross"),
    [
        ("Chandru", 40, "40.00", "0.00", "18000.00"),
        ("Hari", 38, "38.00", "0.00", "17100.00"),
        ("Saran", 42, "40.00", "2.00", "19350.00"),  # 40 x 450 + 2 x 675
    ],
)
def test_the_total_is_paid_with_the_weekly_limit(
    name: str, hours: float, regular: str, overtime: str, gross: str
) -> None:
    [ts] = build_timesheets(total_only(name, hours), CTX)
    recalculate(ts, RULES, set())
    assert ts.entries == []
    assert ts.stated_total == Decimal(str(hours))
    assert ts.regular_hours == Decimal(regular)
    assert ts.overtime_hours == Decimal(overtime)
    assert ts.double_time_hours == ts.holiday_hours == Decimal("0")
    assert (ts.regular_amount or 0) + (ts.overtime_amount or 0) == Decimal(gross)
    assert "no_entries" not in codes(ts.flags)
    assert "weekly_total_only" in codes(ts.flags)


def test_no_dates_anywhere_uses_the_last_full_week_and_says_so() -> None:
    [ts] = build_timesheets(total_only("Chandru", 40), CTX)
    assert ts.week_start == date(2026, 10, 12)  # Mon 12 Oct: the week before Tue 20 Oct
    assert codes(ts.flags) == ["weekly_total_only", "week_assumed"]
    assert "12" in next(f["message"] for f in ts.flags if f["code"] == "week_assumed")


def test_a_week_written_on_the_sheet_is_used_aligned_to_the_company_week() -> None:
    [ts] = build_timesheets(total_only("Hari", 38, week_start=date(2026, 10, 7)), CTX)
    assert ts.week_start == date(2026, 10, 5)  # Wed 7 Oct -> its Monday
    assert "week_assumed" not in codes(ts.flags)


def test_the_company_week_start_is_respected() -> None:
    sunday = BuildContext(
        submission_id=CTX.submission_id,
        document_id=CTX.document_id,
        company_id=None,
        received_on=date(2026, 10, 20),  # Tuesday
        week_start_day=6,  # weeks start on Sunday
    )
    [ts] = build_timesheets(total_only("Saran", 42), sunday)
    assert ts.week_start == date(2026, 10, 11)  # the Sunday-to-Saturday week before


def test_the_email_total_is_still_compared() -> None:
    [ts] = build_timesheets(total_only("Saran", 42, email_stated_total=40), CTX)
    assert "conflicting_hours" in codes(ts.flags)


def test_sheets_with_days_are_unchanged() -> None:
    sheet = ExtractedTimesheet(
        employee_name="Chandru",
        days=[ExtractedDay(work_date=date(2026, 10, 12), hours=8)],
        stated_total=8,
        confidence=0.95,
    )
    [ts] = build_timesheets(sheet, CTX)
    assert len(ts.entries) == 1
    assert "weekly_total_only" not in codes(ts.flags)
    assert weekly_total(ts) is None


def test_no_days_and_no_total_is_still_no_entries() -> None:
    [ts] = build_timesheets(ExtractedTimesheet(employee_name="X", confidence=0.9), CTX)
    assert codes(ts.flags) == ["no_entries"]
    [zero] = build_timesheets(total_only("Y", 0), CTX)
    assert "no_entries" in codes(zero.flags) and not has_hours(zero)


def test_it_has_hours_but_is_never_approved_automatically() -> None:
    [ts] = build_timesheets(total_only("Chandru", 40), CTX)
    recalculate(ts, RULES, set())
    ts.employee_id = uuid.uuid4()
    ts.confidence = Decimal("0.99")
    assert has_hours(ts)
    assert weekly_total(ts) == Decimal("40.00")
    assert not can_auto_approve(ts)


def test_weekly_split_uses_the_company_limit() -> None:
    week = date(2026, 10, 12)
    assert apply_weekly_total(Decimal("42"), week).overtime == Decimal("2")
    loose = PayRules(weekly_ot_after=Decimal("45"))
    result = apply_weekly_total(Decimal("42"), week, loose)
    assert (result.regular, result.overtime) == (Decimal("42.00"), Decimal("0"))


def test_new_flags_are_medium_and_the_prompt_forbids_splitting_totals() -> None:
    assert FLAG_SEVERITY["weekly_total_only"] == Severity.MEDIUM
    assert FLAG_SEVERITY["week_assumed"] == Severity.MEDIUM
    assert "Never split" in SYSTEM_PROMPT and "stated_total" in SYSTEM_PROMPT
