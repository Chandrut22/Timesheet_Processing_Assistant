"""The pay-correctness and workflow fixes from the backend review (bug.md #1-#6, #13)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from src.config.settings import settings
from src.constants.timesheet_status import SubmissionStatus
from src.core.services.export_service import duplicate_problems
from src.core.services.pay_rules import (
    DayInput,
    PayRules,
    apply_pay_rules,
    recalculate,
)
from src.core.services.sweeper import is_stuck
from src.core.services.timesheet_builder import BuildContext, build_timesheets, truncation_flag
from src.core.services.timesheet_validation import _week_lock_key, can_auto_approve
from src.data.models import Employee, Submission, Timesheet, TimesheetEntry
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet

D = Decimal
MON = date(2026, 10, 5)  # a Monday
CTX = BuildContext(
    submission_id=uuid.uuid4(),
    document_id=uuid.uuid4(),
    company_id=None,
    received_on=date(2026, 10, 20),
)


def codes(timesheet: Timesheet) -> set[str]:
    return {str(f.get("code")) for f in timesheet.flags or []}


# --- #3 a sheet over two weeks ------------------------------------------------------


def two_weeks() -> list[DayInput]:
    days = [MON + timedelta(days=i) for i in range(5)]
    days += [MON + timedelta(days=7 + i) for i in range(5)]
    return [DayInput(d, D(8)) for d in days]


def test_weekly_overtime_is_counted_per_week() -> None:
    result = apply_pay_rules(two_weeks())
    assert (result.regular, result.overtime) == (D(80), D(0))  # was 40 + 40


def test_weekly_cap_follows_the_company_week_start() -> None:
    # Week starts on Sunday: Mon-Sat of one week, 7 x 7 h = 49 h -> 9 h overtime
    days = [DayInput(date(2026, 10, 4) + timedelta(days=i), D(7)) for i in range(7)]
    result = apply_pay_rules(days, PayRules(week_start_day=6))
    assert (result.regular, result.overtime) == (D(40), D(9))


def test_a_two_week_sheet_becomes_one_timesheet_per_week() -> None:
    sheet = ExtractedTimesheet(
        employee_name="Grace Okoye",
        days=[ExtractedDay(work_date=d.work_date, hours=8) for d in two_weeks()],
        stated_total=80,
        confidence=0.95,
    )
    parts = build_timesheets(sheet, CTX)
    assert [p.week_start for p in parts] == [MON, MON + timedelta(days=7)]
    assert [len(p.entries) for p in parts] == [5, 5]
    assert all(p.regular_hours == D(40) for p in parts)
    assert all("multi_week_sheet" in codes(p) for p in parts)
    assert all(p.stated_total is None for p in parts)  # the 80 h is for both weeks
    assert all(not can_auto_approve(p) for p in parts)  # a person checks the split


def test_a_one_week_sheet_is_not_split() -> None:
    sheet = ExtractedTimesheet(
        days=[ExtractedDay(work_date=MON + timedelta(days=i), hours=8) for i in range(5)],
        confidence=0.95,
    )
    parts = build_timesheets(sheet, CTX)
    assert len(parts) == 1 and "multi_week_sheet" not in codes(parts[0])


# --- #4 / #5 holidays -----------------------------------------------------------------


def sheet_with(entry: TimesheetEntry) -> Timesheet:
    return Timesheet(flags=[], entries=[entry])


def test_a_deleted_calendar_holiday_is_no_longer_a_holiday() -> None:
    entry = TimesheetEntry(work_date=MON, hours=D(8), sheet_holiday=False)
    timesheet = sheet_with(entry)
    recalculate(timesheet, PayRules(), {MON})
    assert (timesheet.holiday_hours, entry.is_holiday) == (D(8), True)
    recalculate(timesheet, PayRules(), set())  # the holiday was deleted
    assert (timesheet.regular_hours, timesheet.holiday_hours) == (D(8), D(0))
    assert entry.is_holiday is False
    assert "holiday_not_in_calendar" not in codes(timesheet)


def test_a_holiday_marked_on_the_sheet_stays_a_holiday() -> None:
    entry = TimesheetEntry(work_date=MON, hours=D(8), sheet_holiday=True)
    timesheet = sheet_with(entry)
    recalculate(timesheet, PayRules(), set())
    assert timesheet.holiday_hours == D(8)
    assert "holiday_not_in_calendar" in codes(timesheet)


def test_the_builder_records_what_the_sheet_marked() -> None:
    sheet = ExtractedTimesheet(
        days=[ExtractedDay(work_date=MON, hours=8, is_public_holiday=True)], confidence=0.9
    )
    (timesheet,) = build_timesheets(sheet, CTX)
    assert timesheet.entries[0].sheet_holiday is True


# --- #6 long documents ------------------------------------------------------------------


def test_a_cut_document_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_max_input_chars", 100)
    assert truncation_flag("x" * 100) is None
    flag = truncation_flag("x" * 250)
    assert flag is not None and flag["code"] == "document_truncated"
    assert flag["characters"] == 250
    timesheet = Timesheet(flags=[flag])
    assert timesheet.severity == "high"


# --- #1 / #2 paid twice ---------------------------------------------------------------


def employee(name: str, code: str) -> Employee:
    return Employee(id=uuid.uuid4(), full_name=name, employee_code=code)


def test_export_refuses_two_approved_timesheets_for_one_employee() -> None:
    grace, ravi = employee("Grace Okoye", "E001"), employee("Ravi Kumar", "E002")
    pairs = [(Timesheet(id=uuid.uuid4()), grace), (Timesheet(id=uuid.uuid4()), grace)]
    pairs.append((Timesheet(id=uuid.uuid4()), ravi))
    problems = duplicate_problems(pairs, set())
    assert len(problems) == 1 and "Grace Okoye (E001) has 2 approved" in problems[0]


def test_export_refuses_an_employee_already_paid_for_the_week() -> None:
    grace = employee("Grace Okoye", "E001")
    problems = duplicate_problems([(Timesheet(id=uuid.uuid4()), grace)], {grace.id})
    assert len(problems) == 1 and "already paid" in problems[0]
    assert duplicate_problems([(Timesheet(id=uuid.uuid4()), grace)], set()) == []


def test_lock_key_is_stable_and_fits_in_bigint() -> None:
    emp = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = _week_lock_key(emp, MON)
    assert key == _week_lock_key(emp, MON)
    assert key != _week_lock_key(emp, MON + timedelta(days=7))
    assert -(2**63) <= key < 2**63


# --- #13 stuck submissions ------------------------------------------------------------


def submission(status: str, minutes_ago: int) -> Submission:
    now = datetime.now(UTC)
    return Submission(status=status, updated_at=now - timedelta(minutes=minutes_ago))


def test_stuck_means_waiting_or_processing_too_long(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sweeper_grace_seconds", 600)
    monkeypatch.setattr(settings, "worker_stale_after_seconds", 1800)
    now = datetime.now(UTC)
    assert is_stuck(submission(SubmissionStatus.RECEIVED, 11), now)
    assert not is_stuck(submission(SubmissionStatus.RECEIVED, 2), now)
    assert is_stuck(submission(SubmissionStatus.PROCESSING, 31), now)
    assert not is_stuck(submission(SubmissionStatus.PROCESSING, 20), now)
    assert not is_stuck(submission(SubmissionStatus.PROCESSED, 600), now)
