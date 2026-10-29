"""Gross pay: hours x the company's rate for each pay code. No taxes or deductions."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from src.core.services.pay_rules import (
    DayInput,
    PayRules,
    apply_pay_rules,
    price,
    recalculate,
    rules_from_company,
)
from src.core.services.payroll_csv import ExportRow, build_csv, totals
from src.data.models import Company, Timesheet, TimesheetEntry

D = Decimal
MON = date(2026, 10, 5)
ABC = PayRules(
    hourly_rate=D("450"),
    overtime_rate=D("675"),
    holiday_rate=D("900"),
    currency="INR",
)


def test_regular_and_overtime_are_priced() -> None:
    # The example in the design: 40 regular + 2 overtime = 18,000 + 1,350 = 19,350
    amounts = price(D(40), D(2), D(0), D(0), ABC)
    assert amounts.regular == D("18000.00")
    assert amounts.overtime == D("1350.00")
    assert amounts.double_time == D("0.00")
    assert amounts.holiday == D("0.00")
    assert amounts.gross == D("19350.00")


def test_holiday_hours_use_the_holiday_rate() -> None:
    assert price(D(32), D(0), D(0), D(8), ABC).holiday == D("7200.00")


def test_amounts_round_half_up_to_two_decimals() -> None:
    rules = PayRules(hourly_rate=D("333.33"), overtime_rate=D("1"), holiday_rate=D("1"))
    # 7.25 x 333.33 = 2416.6425 -> 2416.64 ; 0.5 x 0.01 style halves round up
    assert price(D("7.25"), D(0), D(0), D(0), rules).regular == D("2416.64")
    rules = PayRules(hourly_rate=D("0.25"), overtime_rate=D("1"), holiday_rate=D("1"))
    assert price(D("0.10"), D(0), D(0), D(0), rules).regular == D(
        "0.03"
    )  # 0.025 -> 0.03


def test_no_company_means_no_amounts() -> None:
    amounts = price(D(40), D(0), D(0), D(0), PayRules())
    assert amounts.regular is None
    assert amounts.gross is None


def test_double_time_without_a_rate_is_not_priced() -> None:
    amounts = price(D(30), D(0), D(4), D(0), ABC)  # ABC has no double-time rate
    assert amounts.regular == D("13500.00")
    assert amounts.double_time is None
    assert amounts.gross is None
    assert amounts.missing == ["double_time"]


def test_zero_hours_need_no_rate() -> None:
    assert price(D(40), D(0), D(0), D(0), ABC).double_time == D("0.00")


def test_pay_rules_then_price_a_long_week() -> None:
    days = [
        DayInput(MON + timedelta(days=i), D(h)) for i, h in enumerate([10, 8, 8, 8, 8])
    ]
    result = apply_pay_rules(days, ABC)  # 10 h Monday -> 2 h overtime
    amounts = price(
        result.regular, result.overtime, result.double_time, result.holiday, ABC
    )
    assert (result.regular, result.overtime) == (D(40), D(2))
    assert amounts.gross == D("19350.00")


def _company(**kw: object) -> Company:
    values: dict[str, object] = {
        "name": "ABC Staffing",
        "hourly_rate": D("450"),
        "overtime_rate": D("675"),
        "double_time_rate": None,
        "holiday_rate": D("900"),
        "currency": "INR",
        "daily_ot_after": D(8),
        "weekly_ot_after": D(40),
        "double_time_after": None,
    }
    values.update(kw)
    return Company(**values)


def _timesheet(*hours: str, double_time_marked: bool = False) -> Timesheet:
    timesheet = Timesheet(flags=[])
    timesheet.entries = [
        TimesheetEntry(
            work_date=MON + timedelta(days=i),
            hours=D(h),
            double_time_marked=double_time_marked,
        )
        for i, h in enumerate(hours)
    ]
    return timesheet


def test_recalculate_copies_rates_and_stores_amounts() -> None:
    timesheet = _timesheet("10", "8", "8", "8", "8")
    recalculate(timesheet, rules_from_company(_company()), set())
    assert timesheet.currency == "INR"
    assert timesheet.hourly_rate == D("450")
    assert timesheet.regular_amount == D("18000.00")
    assert timesheet.overtime_amount == D("1350.00")
    assert not any(f["code"] == "missing_rate" for f in timesheet.flags)


def test_recalculate_flags_a_missing_rate() -> None:
    timesheet = _timesheet("6", double_time_marked=True)
    recalculate(timesheet, rules_from_company(_company()), set())
    assert timesheet.double_time_amount is None
    flag = next(f for f in timesheet.flags if f["code"] == "missing_rate")
    assert flag["severity"] == "high"
    assert flag["pay_codes"] == ["double_time"]


def test_recalculate_again_after_the_rate_is_added_clears_the_flag() -> None:
    timesheet = _timesheet("6", double_time_marked=True)
    recalculate(timesheet, rules_from_company(_company()), set())
    company = _company(double_time_rate=D("900"))
    recalculate(timesheet, rules_from_company(company), set())
    assert timesheet.double_time_amount == D("5400.00")
    assert not any(f["code"] == "missing_rate" for f in timesheet.flags)


def test_recalculate_without_company_stores_no_amounts_and_no_rate_flag() -> None:
    timesheet = _timesheet("8")
    recalculate(timesheet, rules_from_company(None), set(), default_rules_used=True)
    assert timesheet.regular_amount is None
    assert timesheet.currency is None
    codes = [f["code"] for f in timesheet.flags]
    assert "default_rules" in codes
    assert "missing_rate" not in codes


def _row(code: str, regular: str, overtime: str, priced: bool = True) -> ExportRow:
    reg, ot = D(regular), D(overtime)
    return ExportRow(
        timesheet_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        employee_code=code,
        employee_name=f"Employee {code}",
        regular=reg,
        overtime=ot,
        double_time=D(0),
        holiday=D(0),
        approved_by="Ravi",
        approved_at=datetime(2026, 10, 12, tzinfo=UTC),
        currency="INR",
        hourly_rate=D("450"),
        overtime_rate=D("675"),
        holiday_rate=D("900"),
        regular_amount=(reg * 450).quantize(D("0.01")) if priced else None,
        overtime_amount=(ot * 675).quantize(D("0.01")),
        double_time_amount=D("0.00"),
        holiday_amount=D("0.00"),
    )


def test_csv_has_rates_amounts_and_gross() -> None:
    text = build_csv("ABC", MON, [_row("E1", "40", "2")])
    header, line = text.splitlines()[:2]
    cells = dict(zip(header.split(","), line.split(","), strict=True))
    assert cells["currency"] == "INR"
    assert cells["hourly_rate"] == "450.00"
    assert cells["regular_amount"] == "18000.00"
    assert cells["overtime_amount"] == "1350.00"
    assert cells["gross_amount"] == "19350.00"
    assert cells["double_time_rate"] == ""  # no rate -> empty cell


def test_totals_add_up_the_money_and_count_unpriced_rows() -> None:
    t = totals(
        [
            _row("E1", "40", "2"),
            _row("E2", "40", "0"),
            _row("E3", "8", "0", priced=False),
        ]
    )
    assert t.gross == D("37350.00")  # 19,350 + 18,000; E3 not counted
    assert t.unpriced == 1
