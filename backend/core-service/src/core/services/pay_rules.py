"""Pay rules: split worked hours into regular, overtime, double time and holiday,
then price them with the company's pay rates (gross pay, no taxes or deductions).

apply_pay_rules() and price() are pure (no database, no LLM), so every rule is unit-tested.

Per day, in this order:
  1. Holiday (marked on the sheet or in the holiday calendar) -> all hours holiday hours
  2. Marked as double time on the sheet                       -> all hours double time
  3. Otherwise: the first daily_ot_after hours are regular, the rest overtime,
     and hours above double_time_after (if the company has that rule) double time.
Then for the week:
  4. Regular hours above weekly_ot_after become overtime, taken from the LATEST
     days first (the hours that pushed the week over the limit).
Then the money:
  5. amount = hours x the company's rate for that pay code, rounded to 2 decimals.
     gross = the four amounts added up. No company -> no amounts.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.data.models import Company, Timesheet

ZERO = Decimal("0")
CENT = Decimal("0.01")

# Flags this module owns: removed and recomputed on every recalculation.
RULE_FLAG_CODES = frozenset(
    {"holiday_worked", "holiday_not_in_calendar", "default_rules", "missing_rate"}
)


@dataclass(frozen=True, slots=True)
class PayRules:
    daily_ot_after: Decimal = Decimal("8")
    weekly_ot_after: Decimal = Decimal("40")
    double_time_after: Decimal | None = None  # None = no double-time rule
    # Pay per hour for each pay code. None = unknown (no company -> nothing is priced).
    hourly_rate: Decimal | None = None
    overtime_rate: Decimal | None = None
    double_time_rate: Decimal | None = None
    holiday_rate: Decimal | None = None
    currency: str | None = None

    @property
    def has_rates(self) -> bool:
        return self.hourly_rate is not None


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


@dataclass(frozen=True, slots=True)
class PayAmounts:
    """Money per pay code. None = could not be priced (no company, or no rate)."""

    regular: Decimal | None = None
    overtime: Decimal | None = None
    double_time: Decimal | None = None
    holiday: Decimal | None = None

    @property
    def gross(self) -> Decimal | None:
        parts = (self.regular, self.overtime, self.double_time, self.holiday)
        if any(p is None for p in parts):
            return None
        return sum((p for p in parts if p is not None), ZERO)

    @property
    def missing(self) -> list[str]:
        """Pay codes that have hours but no rate."""
        names = ("regular", "overtime", "double_time", "holiday")
        return [n for n in names if getattr(self, n) is None]


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


def _amount(hours: Decimal, rate: Decimal | None) -> Decimal | None:
    if hours == ZERO:
        return ZERO.quantize(CENT)  # no hours -> nothing to pay, rate or not
    if rate is None:
        return None
    return (hours * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def price(
    regular: Decimal,
    overtime: Decimal,
    double_time: Decimal,
    holiday: Decimal,
    rules: PayRules,
) -> PayAmounts:
    """Hours x rate per pay code. Without company rates nothing is priced."""
    if not rules.has_rates:
        return PayAmounts()
    return PayAmounts(
        regular=_amount(regular, rules.hourly_rate),
        overtime=_amount(overtime, rules.overtime_rate),
        double_time=_amount(double_time, rules.double_time_rate),
        holiday=_amount(holiday, rules.holiday_rate),
    )


# --- glue to the models (still no database access) ------------------------------


def rules_from_company(company: Company | None) -> PayRules:
    if company is None:
        return DEFAULT_RULES
    return PayRules(
        daily_ot_after=company.daily_ot_after,
        weekly_ot_after=company.weekly_ot_after,
        double_time_after=company.double_time_after,
        hourly_rate=company.hourly_rate,
        overtime_rate=company.overtime_rate,
        double_time_rate=company.double_time_rate,
        holiday_rate=company.holiday_rate,
        currency=company.currency,
    )


def _store_pay(timesheet: Timesheet, rules: PayRules, amounts: PayAmounts) -> None:
    """Copy the rates used onto the timesheet, so a later rate change never alters it."""
    timesheet.currency = rules.currency
    timesheet.hourly_rate = rules.hourly_rate
    timesheet.overtime_rate = rules.overtime_rate
    timesheet.double_time_rate = rules.double_time_rate
    timesheet.holiday_rate = rules.holiday_rate
    timesheet.regular_amount = amounts.regular
    timesheet.overtime_amount = amounts.overtime
    timesheet.double_time_amount = amounts.double_time
    timesheet.holiday_amount = amounts.holiday


def recalculate(
    timesheet: Timesheet,
    rules: PayRules,
    holidays: Collection[date],
    *,
    default_rules_used: bool = False,
) -> PayResult:
    """Mark holidays, split the hours, price them, store the totals and flags.

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

    amounts = price(result.regular, result.overtime, result.double_time, result.holiday, rules)
    _store_pay(timesheet, rules, amounts)

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
    if rules.has_rates and amounts.missing:
        names = ", ".join(n.replace("_", "-") for n in amounts.missing)
        flags.append(
            {
                "code": "missing_rate",
                "message": (
                    f"There are {names} hours but the company has no {names} rate, so the "
                    "pay cannot be calculated. Add the rate to the company, then recalculate."
                ),
                "pay_codes": amounts.missing,
            }
        )
    timesheet.flags = flags  # a new list, so SQLAlchemy saves the JSONB change
    return result
