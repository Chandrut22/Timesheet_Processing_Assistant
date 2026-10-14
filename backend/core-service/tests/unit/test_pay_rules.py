from datetime import date, timedelta
from decimal import Decimal

from src.core.services.pay_rules import DayInput, PayRules, apply_pay_rules

MON = date(2026, 10, 5)
D = Decimal


def week(*hours: float, start: date = MON) -> list[DayInput]:
    return [DayInput(start + timedelta(days=i), D(str(h))) for i, h in enumerate(hours)]


def totals(result) -> tuple[Decimal, Decimal, Decimal]:  # type: ignore[no-untyped-def]
    return result.regular, result.overtime, result.double_time


def test_normal_week_is_all_regular() -> None:
    assert totals(apply_pay_rules(week(8, 8, 8, 8, 8))) == (D(40), D(0), D(0))


def test_daily_overtime() -> None:
    # 9 h each day: 1 h OT per day, 40 regular -> no weekly excess
    assert totals(apply_pay_rules(week(9, 9, 9, 9, 9))) == (D(40), D(5), D(0))


def test_double_time_after_12_hours() -> None:
    rules = PayRules(double_time_after=D(12))
    assert totals(apply_pay_rules(week(13), rules)) == (D(8), D(4), D(1))


def test_long_day_without_double_time_rule_is_overtime() -> None:
    assert totals(apply_pay_rules(week(13))) == (D(8), D(5), D(0))


def test_weekly_cap_moves_latest_day_to_overtime() -> None:
    result = apply_pay_rules(week(8, 8, 8, 8, 8, 8))  # Mon-Sat
    assert totals(result) == (D(40), D(8), D(0))
    saturday = result.days[-1]
    assert (saturday.regular, saturday.overtime) == (D(0), D(8))


def test_weekly_cap_takes_partial_day() -> None:
    result = apply_pay_rules(week(8, 8, 8, 8, 8, 4))  # 44 h
    assert totals(result) == (D(40), D(4), D(0))
    assert result.days[-1].overtime == D(4)


def test_holiday_hours_are_overtime() -> None:
    days = [DayInput(MON, D(8), is_holiday=True), DayInput(MON + timedelta(1), D(8))]
    assert totals(apply_pay_rules(days)) == (D(8), D(8), D(0))


def test_marked_double_time() -> None:
    days = [DayInput(MON, D(6), double_time_marked=True)]
    assert totals(apply_pay_rules(days)) == (D(0), D(0), D(6))


def test_custom_company_rules() -> None:
    rules = PayRules(daily_ot_after=D(10), weekly_ot_after=D(38))
    # 4 x 10 h = 40 regular by day, weekly cap 38 -> 2 h OT from the last day
    assert totals(apply_pay_rules(week(10, 10, 10, 10), rules)) == (D(38), D(2), D(0))


def test_total_is_preserved() -> None:
    rules = PayRules(double_time_after=D(12))
    result = apply_pay_rules(week(13, 11, 8, 9, 10, 6), rules)
    assert result.total == D(57)
