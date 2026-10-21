"""Turn one ExtractedTimesheet into a Timesheet + entries, adding flags for anything odd.

Pure function: no database, no LLM. The pay rules (regular / overtime / double time /
holiday) run afterwards in pay_rules.recalculate(); here every hour starts as 'regular'.

Payroll works per employee per week, so a sheet listing days from more than one week
is split into one timesheet per week (build_timesheets).

A sheet that gives only a weekly total per person ("Chandru 40 h", no days) becomes a
timesheet with no days whose hours are that total (flag weekly_total_only; the pay rules
then apply the weekly limit only, see pay_rules.apply_weekly_total). Its week is the one
written on the sheet, or else the last full week before the email arrived (flag
week_assumed). It is never approved automatically."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.config.settings import settings
from src.constants.timesheet_status import TimesheetStatus
from src.core.services.pay_rules import WEEK_ASSUMED_FLAG, WEEKLY_TOTAL_FLAG
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
    is_email_body: bool = False  # the "document" is the email text itself (no attachment)


def _flag(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _hours(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def conflicting_hours_flag(
    email_total: Decimal | None, attachment_total: Decimal
) -> dict[str, Any] | None:
    """Pure: the email says one total, the attachment another -> flag with BOTH values."""
    if email_total is None or email_total == attachment_total:
        return None
    return {
        "code": "conflicting_hours",
        "message": f"The email says {float(email_total):g} h but the attachment says "
        f"{float(attachment_total):g} h. Check which is right.",
        "email_hours": float(email_total),
        "attachment_hours": float(attachment_total),
    }


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


def _total_week(extracted: ExtractedTimesheet, ctx: BuildContext) -> tuple[date, bool]:
    """The week of a weekly-total-only sheet: (first day, assumed?). The week written on
    the sheet, else the last full week before the email arrived (timesheets are sent
    after the week)."""
    if extracted.week_start is not None:
        return start_of_week(extracted.week_start, ctx.week_start_day), False
    return start_of_week(ctx.received_on, ctx.week_start_day) - timedelta(days=7), True


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
            existing.sheet_holiday = bool(existing.sheet_holiday) or day.is_public_holiday
            existing.is_holiday = existing.sheet_holiday
            flags.append(
                _flag("duplicate_day", f"{work_date} appears more than once; hours added.")
            )
        else:
            entries[work_date] = TimesheetEntry(
                work_date=work_date,
                hours=hours,
                double_time_marked=day.double_time_marked,
                is_holiday=day.is_public_holiday,  # calendar added by recalculate()
                sheet_holiday=day.is_public_holiday,  # as marked on the sheet
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
    ordered = sorted(entries.values(), key=lambda e: e.work_date)
    total = sum((e.hours for e in ordered), Decimal("0"))
    stated = _hours(extracted.stated_total) if extracted.stated_total is not None else None
    # Only a weekly total, no days ("Chandru 40 h"): the total is the hours.
    weekly_only = not ordered and stated is not None and stated > 0
    total_week: date | None = None
    if weekly_only:
        assert stated is not None
        total, (total_week, week_assumed) = stated, _total_week(extracted, ctx)
        flags.append(
            _flag(
                WEEKLY_TOTAL_FLAG,
                f"The sheet gives only a weekly total ({stated} h), no daily hours. Overtime "
                "comes from the weekly limit only; daily overtime, double time and holidays "
                "could not be applied. Add the days if you know them.",
            )
        )
        if week_assumed:
            flags.append(
                _flag(
                    WEEK_ASSUMED_FLAG,
                    f"No dates on the sheet or in the email: used the last full week before "
                    f"it arrived (starting {total_week}). Change the week if it is wrong.",
                )
            )
    elif not ordered:
        flags.append(_flag("no_entries", "No hours could be read from this timesheet."))
    if stated is not None and ordered and stated != total:
        flags.append(
            _flag("total_mismatch", f"Sheet says {stated} h; the days add up to {total} h.")
        )

    email_total = (
        _hours(extracted.email_stated_total)
        if extracted.email_stated_total is not None and not ctx.is_email_body
        else None
    )
    if ordered or weekly_only:
        conflict = conflicting_hours_flag(email_total, stated if stated is not None else total)
        if conflict:
            flags.append(conflict)

    week_start = (
        start_of_week(ordered[0].work_date, ctx.week_start_day)
        if ordered
        else total_week or extracted.week_start
    )
    read_confidence = Decimal(str(round(extracted.confidence, 2)))

    return Timesheet(
        submission_id=ctx.submission_id,
        document_id=ctx.document_id,
        company_id=ctx.company_id,
        extracted_name=(extracted.employee_name or None) and extracted.employee_name[:200],
        extracted_code=(extracted.employee_code or None) and extracted.employee_code[:50],
        extracted_company_name=(extracted.company_name or None) and extracted.company_name[:200],
        email_stated_total=email_total,
        week_start=week_start,
        status=TimesheetStatus.NEEDS_REVIEW,  # the auto-approve decision comes later
        regular_hours=total,  # split into OT / DT / holiday by pay_rules.recalculate()
        overtime_hours=Decimal("0"),
        double_time_hours=Decimal("0"),
        holiday_hours=Decimal("0"),
        stated_total=stated,
        read_confidence=read_confidence,
        confidence=read_confidence,  # lowered by the match (employee_matcher.apply_match)
        flags=flags,
        entries=ordered,
    )


def split_by_week(timesheet: Timesheet, week_start_day: int = 0) -> list[Timesheet]:
    """One timesheet per week. A sheet that covers a single week comes back unchanged.

    Each part keeps the sheet's flags and gets a multi_week_sheet flag (so a reviewer
    checks it). The sheet's stated total and the email's total belong to the whole
    sheet, so the parts do not carry them; the whole-sheet checks (total_mismatch,
    conflicting_hours) were already made in build_timesheet."""
    entries = list(timesheet.entries)
    weeks: dict[date, list[TimesheetEntry]] = {}
    for entry in entries:
        weeks.setdefault(start_of_week(entry.work_date, week_start_day), []).append(entry)
    if len(weeks) <= 1:
        return [timesheet]

    timesheet.entries = []  # the entries move to the parts
    starts = sorted(weeks)
    listed = ", ".join(str(w) for w in starts)
    parts: list[Timesheet] = []
    for number, week in enumerate(starts, start=1):
        days = sorted(weeks[week], key=lambda e: e.work_date)
        flag = _flag(
            "multi_week_sheet",
            f"The sheet covers {len(starts)} weeks (starting {listed}); it was split into "
            f"one timesheet per week. This is week {number} of {len(starts)}"
            + (
                f" (the sheet's total of {timesheet.stated_total} h is for all weeks)."
                if timesheet.stated_total is not None
                else "."
            ),
        )
        parts.append(
            Timesheet(
                submission_id=timesheet.submission_id,
                document_id=timesheet.document_id,
                company_id=timesheet.company_id,
                extracted_name=timesheet.extracted_name,
                extracted_code=timesheet.extracted_code,
                extracted_company_name=timesheet.extracted_company_name,
                email_stated_total=None,
                week_start=week,
                status=TimesheetStatus.NEEDS_REVIEW,
                regular_hours=sum((e.hours for e in days), Decimal("0")),
                overtime_hours=Decimal("0"),
                double_time_hours=Decimal("0"),
                holiday_hours=Decimal("0"),
                stated_total=None,
                read_confidence=timesheet.read_confidence,
                confidence=timesheet.confidence,
                flags=[*(dict(f) for f in timesheet.flags or []), flag],
                entries=days,
            )
        )
    return parts


def build_timesheets(extracted: ExtractedTimesheet, ctx: BuildContext) -> list[Timesheet]:
    """build_timesheet, then one timesheet per week."""
    return split_by_week(build_timesheet(extracted, ctx), ctx.week_start_day)


def truncation_flag(text: str) -> dict[str, Any] | None:
    """The AI only sees the first llm_max_input_chars characters: say so when it was cut."""
    limit = settings.llm_max_input_chars
    if len(text) <= limit:
        return None
    return {
        "code": "document_truncated",
        "message": f"The document is too long ({len(text):,} characters); only the first "
        f"{limit:,} were read. Later pages or employees may be missing. Check the original.",
        "characters": len(text),
        "read_characters": limit,
    }
