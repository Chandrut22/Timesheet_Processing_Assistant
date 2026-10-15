"""Turn one ExtractedTimesheet into a Timesheet + entries, adding flags for anything odd.

Pure function: no database, no LLM. The pay rules (regular / overtime / double time /
holiday) run afterwards in pay_rules.recalculate(); here every hour starts as 'regular'."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.constants.timesheet_status import TimesheetStatus
from src.data.models import Timesheet, TimesheetEntry
from src.schemas.extraction import ExtractedTimesheet
from src.utils.dates import date_in_week, start_of_week, weekday_index

MAX_DAY = Decimal("24")
LONG_DAY = Decimal("16")
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class BuildContext:
    submission_id: uuid.UUID
    document_id: uuid.UUID
    company_id: uuid.UUID | None
    received_on: date
    week_start_day: int = 0  # from the company; 0 = Monday


def _flag(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _hours(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _base_week(extracted: ExtractedTimesheet, ctx: BuildContext) -> tuple[date | None, bool]:
    """Which week do weekday-only days ('Mon 8') belong to? Returns (first day, assumed?)."""
    if extracted.week_start is not None:
        return extracted.week_start, False
    weekdays = [weekday_index(d.weekday) for d in extracted.days if d.work_date is None]
    known = [w for w in weekdays if w is not None]
    if not known:
        return None, False
    # The week the email arrived; the week before if that would put days in the future.
    base = start_of_week(ctx.received_on, ctx.week_start_day)
    if any(date_in_week(base, w) > ctx.received_on for w in known):
        base -= timedelta(days=7)
    return base, True


def build_timesheet(extracted: ExtractedTimesheet, ctx: BuildContext) -> Timesheet:
    flags = [_flag("model_issue", issue) for issue in extracted.issues]
    base, assumed = _base_week(extracted, ctx)
    entries: dict[date, TimesheetEntry] = {}
    undated = 0

    for day in extracted.days:
        work_date = day.work_date
        if work_date is None:
            index = weekday_index(day.weekday)
            if index is None or base is None:
                undated += 1
                continue
            work_date = date_in_week(base, index)

        hours = _hours(day.hours)
        if work_date in entries:  # the same day listed twice: add up, but say so
            existing = entries[work_date]
            existing.hours += hours
            existing.is_holiday = bool(existing.is_holiday) or day.is_public_holiday
            flags.append(
                _flag("duplicate_day", f"{work_date} appears more than once; hours added.")
            )
        else:
            entries[work_date] = TimesheetEntry(
                work_date=work_date,
                hours=hours,
                double_time_marked=day.double_time_marked,
                is_holiday=day.is_public_holiday,  # as marked on the sheet
                note=day.note[:255] if day.note else None,
            )

    for entry in entries.values():
        if entry.hours > MAX_DAY:
            flags.append(_flag("day_over_24", f"{entry.work_date}: {entry.hours} h, capped at 24."))
            entry.hours = MAX_DAY
        elif entry.hours > LONG_DAY:
            flags.append(
                _flag("long_day", f"{entry.work_date}: {entry.hours} h in one day. Please confirm.")
            )

    if assumed and entries:
        flags.append(_flag("dates_assumed", f"No dates on the sheet; used the week of {base}."))
    if undated:
        flags.append(
            _flag("undated_days", f"{undated} day(s) had no readable date and were skipped.")
        )
    if not entries:
        flags.append(_flag("no_entries", "No hours could be read from this timesheet."))

    ordered = sorted(entries.values(), key=lambda e: e.work_date)
    total = sum((e.hours for e in ordered), Decimal("0"))
    stated = _hours(extracted.stated_total) if extracted.stated_total is not None else None
    if stated is not None and ordered and stated != total:
        flags.append(
            _flag("total_mismatch", f"Sheet says {stated} h; the days add up to {total} h.")
        )

    week_start = (
        start_of_week(ordered[0].work_date, ctx.week_start_day) if ordered else extracted.week_start
    )

    return Timesheet(
        submission_id=ctx.submission_id,
        document_id=ctx.document_id,
        company_id=ctx.company_id,
        extracted_name=(extracted.employee_name or None) and extracted.employee_name[:200],
        extracted_code=(extracted.employee_code or None) and extracted.employee_code[:50],
        week_start=week_start,
        status=TimesheetStatus.NEEDS_REVIEW,  # the auto-approve decision comes later
        regular_hours=total,  # split into OT / DT / holiday by pay_rules.recalculate()
        overtime_hours=Decimal("0"),
        double_time_hours=Decimal("0"),
        holiday_hours=Decimal("0"),
        stated_total=stated,
        confidence=Decimal(str(round(extracted.confidence, 2))),
        flags=flags,
        entries=ordered,
    )
