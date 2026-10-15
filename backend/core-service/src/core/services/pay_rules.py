"""Pay rules: split worked hours into regular, overtime, double time and holiday.

apply_pay_rules() is pure (no database, no LLM), so every rule is unit-tested.

Per day, in this order:
  1. Holiday (marked on the sheet or in the holiday calendar) -> all hours holiday hours
  2. Marked as double time on the sheet                       -> all hours double time
  3. Otherwise: the first daily_ot_after hours are regular, the rest overtime,
     and hours above double_time_after (if the company has that rule) double time.
Then for the week:
  4. Regular hours above weekly_ot_after become overtime, taken from the LATEST
     days first (the hours that pushed the week over the limit).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from src.data.models import Company, Timesheet

ZERO = Decimal("0")

# Flags this module owns: removed and recomputed on every recalculation.
RULE_FLAG_CODES = frozenset({"holiday_worked", "holiday_not_in_calendar", "default_rules"})


@dataclass(frozen=True, slots=True)
class PayRules:
    daily_ot_after: Decimal = Decimal("8")
    weekly_ot_after: Decimal = Decimal("40")
    double_time_after: Decimal | None = None  # None = no double-time rule


DEFAULT_RULES = PayRules()


@dataclass(frozen=True, slots=True)
class DayInput:
    work_date: date
    hours: Decimal
    double_time_marked: bool = False
    is_holiday: bool = False


@dataclass(slots=True)
class DaySplit:
    work_date: date
    regular: Decimal = ZERO
    overtime: Decimal = ZERO
    double_time: Decimal = ZERO
    holiday: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class PayResult:
    days: list[DaySplit]

    @property
    def regular(self) -> Decimal:
        return sum((d.regular for d in self.days), ZERO)

    @property
    def overtime(self) -> Decimal:
        return sum((d.overtime for d in self.days), ZERO)

    @property
    def double_time(self) -> Decimal:
        return sum((d.double_time for d in self.days), ZERO)

    @property
    def holiday(self) -> Decimal:
        return sum((d.holiday for d in self.days), ZERO)

    @property
    def total(self) -> Decimal:
        return self.regular + self.overtime + self.double_time + self.holiday


def _split_day(day: DayInput, rules: PayRules) -> DaySplit:
    split = DaySplit(work_date=day.work_date)
    hours = day.hours

    if day.is_holiday:
        split.holiday = hours
        return split
    if day.double_time_marked:
        split.double_time = hours
        return split

    split.regular = min(hours, rules.daily_ot_after)
    above_regular = hours - split.regular
    if rules.double_time_after is not None and hours > rules.double_time_after:
        split.double_time = hours - rules.double_time_after
        above_regular -= split.double_time
    split.overtime = above_regular
    return split


def apply_pay_rules(days: Sequence[DayInput], rules: PayRules = DEFAULT_RULES) -> PayResult:
    splits = [_split_day(day, rules) for day in sorted(days, key=lambda d: d.work_date)]

    # Weekly cap: move regular hours above the limit to overtime, latest days first.
    excess = sum((s.regular for s in splits), ZERO) - rules.weekly_ot_after
    for split in reversed(splits):
        if excess <= ZERO:
            break
        moved = min(split.regular, excess)
        split.regular -= moved
        split.overtime += moved
        excess -= moved

    return PayResult(days=splits)


# --- glue to the models (still no database access) ------------------------------


def rules_from_company(company: Company | None) -> PayRules:
    if company is None:
        return DEFAULT_RULES
    return PayRules(
        daily_ot_after=company.daily_ot_after,
        weekly_ot_after=company.weekly_ot_after,
        double_time_after=company.double_time_after,
    )


def recalculate(
    timesheet: Timesheet,
    rules: PayRules,
    holidays: Collection[date],
    *,
    default_rules_used: bool = False,
) -> PayResult:
    """Mark holidays, split the hours, store the totals and flags.

    A day is a holiday if the sheet marks it OR it is in the holiday calendar.
    Safe to call again after a reviewer edits hours: rule flags are rebuilt."""
    for entry in timesheet.entries:
        entry.is_holiday = bool(entry.is_holiday) or entry.work_date in holidays

    result = apply_pay_rules(
        [
            DayInput(e.work_date, e.hours, e.double_time_marked, e.is_holiday)
            for e in timesheet.entries
        ],
        rules,
    )
    timesheet.regular_hours = result.regular
    timesheet.overtime_hours = result.overtime
    timesheet.double_time_hours = result.double_time
    timesheet.holiday_hours = result.holiday

    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in RULE_FLAG_CODES
    ]
    for entry in timesheet.entries:
        if not entry.is_holiday or entry.hours <= ZERO:
            continue
        if entry.work_date in holidays:
            flags.append(
                {
                    "code": "holiday_worked",
                    "message": f"{entry.work_date}: {entry.hours} h on a holiday.",
                }
            )
        else:
            flags.append(
                {
                    "code": "holiday_not_in_calendar",
                    "message": (
                        f"{entry.work_date} is marked as a holiday on the sheet but is not "
                        "in the holiday calendar. Check it."
                    ),
                }
            )
    if default_rules_used:
        flags.append(
            {
                "code": "default_rules",
                "message": "No company set: default rules used (OT after 8 h/day, 40 h/week).",
            }
        )
    timesheet.flags = flags  # a new list, so SQLAlchemy saves the JSONB change
    return result
