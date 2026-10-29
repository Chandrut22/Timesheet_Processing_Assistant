"""Holiday pay, as the use case asks:

- worked on a holiday of the employee's company -> paid at the holiday rate, flagged
  holiday_worked (medium, with the holiday's name) and sent to review
- a holiday not worked (no day, or 0 h) -> nothing: no flag, no pay line, can
  auto-approve
- a weekly-total sheet (no days) in a holiday week -> holiday_in_week, sent to review"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from src.core.services.pay_rules import (
    WEEKLY_TOTAL_FLAG,
    recalculate,
    rules_from_company,
)
from src.core.services.timesheet_validation import can_auto_approve
from src.data.models import Company, Timesheet, TimesheetEntry

MON = date(2026, 10, 12)
TUE = MON + timedelta(days=1)
FOUNDATION_DAY = {TUE: "Foundation Day"}
D = Decimal


def company() -> Company:
    return Company(
        name="ABC Staffing",
        hourly_rate=D("450"),
        overtime_rate=D("675"),
        holiday_rate=D("900"),
        currency="INR",
        daily_ot_after=D(8),
        weekly_ot_after=D(40),
    )


def week(*hours: str) -> Timesheet:
    t = Timesheet(
        employee_id=uuid.uuid4(), confidence=D("0.95"), flags=[], week_start=MON
    )
    t.entries = [
        TimesheetEntry(work_date=MON + timedelta(days=i), hours=D(h))
        for i, h in enumerate(hours)
    ]
    return t


def codes(t: Timesheet) -> list[str]:
    return [f["code"] for f in t.flags]


def test_a_worked_holiday_is_paid_at_the_holiday_rate_and_reviewed() -> None:
    t = week("8", "8", "8", "8", "8")
    recalculate(t, rules_from_company(company()), FOUNDATION_DAY)
    assert (t.regular_hours, t.holiday_hours) == (D(32), D(8))
    assert t.holiday_amount == D("7200.00") and t.regular_amount == D("14400.00")
    (flag,) = [f for f in t.flags if f["code"] == "holiday_worked"]
    assert flag["severity"] == "medium"
    assert flag["message"] == (
        "2026-10-13: 8 h on a holiday (Foundation Day), paid at the holiday rate. "
        "Check it."
    )
    assert flag["date"] == "2026-10-13"
    assert not can_auto_approve(t)  # a person checks holiday pay


def test_a_holiday_not_worked_changes_nothing() -> None:
    zero = week("8", "0", "8", "8", "8")  # the holiday is on the sheet with 0 h
    recalculate(zero, rules_from_company(company()), FOUNDATION_DAY)
    missing = week("8")  # the holiday is not on the sheet at all
    missing.entries = [TimesheetEntry(work_date=MON, hours=D(8))]
    recalculate(missing, rules_from_company(company()), FOUNDATION_DAY)
    for t in (zero, missing):
        assert codes(t) == []
        assert t.holiday_hours == D(0) and not t.holiday_amount  # no holiday pay
        assert can_auto_approve(t)


def test_another_companys_holiday_has_no_effect() -> None:
    t = week("8", "8", "8", "8", "8")
    recalculate(
        t, rules_from_company(company()), {}
    )  # this company has no holiday that day
    assert t.holiday_hours == D(0) and codes(t) == []
    assert can_auto_approve(t)


def test_a_weekly_total_in_a_holiday_week_is_reviewed() -> None:
    t = Timesheet(
        employee_id=uuid.uuid4(),
        confidence=D("0.95"),
        flags=[{"code": WEEKLY_TOTAL_FLAG, "message": "weekly total"}],
        week_start=MON,
        stated_total=D(40),
    )
    t.entries = []
    recalculate(t, rules_from_company(company()), FOUNDATION_DAY)
    (flag,) = [f for f in t.flags if f["code"] == "holiday_in_week"]
    assert "13 Oct (Foundation Day)" in flag["message"] and flag["dates"] == [
        "2026-10-13"
    ]
    assert t.regular_hours == D(40) and t.holiday_hours == D(0)  # no days: can't tell
    assert not can_auto_approve(t)

    recalculate(t, rules_from_company(company()), {date(2026, 10, 20): "Next week"})
    assert "holiday_in_week" not in codes(t)  # recomputed: another week's holiday


def test_a_plain_set_of_dates_still_works() -> None:
    t = week("8", "8")
    recalculate(t, rules_from_company(company()), {TUE})
    (flag,) = [f for f in t.flags if f["code"] == "holiday_worked"]
    assert (
        flag["message"]
        == "2026-10-13: 8 h on a holiday, paid at the holiday rate. Check it."
    )
