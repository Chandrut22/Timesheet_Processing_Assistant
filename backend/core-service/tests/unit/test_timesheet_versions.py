"""Days stored as JSONB on the timesheet, and the version snapshots used for history
and rollback."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.constants.timesheet_status import TimesheetChange, TimesheetStatus
from src.core.services.pay_rules import PayRules, recalculate
from src.core.services.version_history import (
    data_changed,
    restore_snapshot,
    save_version,
    summary,
    take_snapshot,
)
from src.data.models import Timesheet, TimesheetEntry, TimesheetVersion
from src.data.models.timesheet_entry import EntryList, check_entries

MON = date(2026, 10, 12)
TUE = date(2026, 10, 13)


def day(when: date, hours: str = "8", **extra: object) -> TimesheetEntry:
    return TimesheetEntry(work_date=when, hours=Decimal(hours), **extra)  # type: ignore[arg-type]


def sheet(**extra: object) -> Timesheet:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "version": 1,
        "status": TimesheetStatus.NEEDS_REVIEW,
        "extracted_name": "Grace Hopper",
        "employee_id": uuid.uuid4(),
        "week_start": MON,
        "regular_hours": Decimal("15.50"),
        "overtime_hours": Decimal("0"),
        "double_time_hours": Decimal("0"),
        "holiday_hours": Decimal("0"),
        "regular_amount": Decimal("6975.00"),
        "overtime_amount": Decimal("0"),
        "double_time_amount": Decimal("0"),
        "holiday_amount": Decimal("0"),
        "flags": [{"code": "long_day", "message": "x"}],
        "entries": [day(TUE, "7.5", note="late"), day(MON)],
    }
    values.update(extra)
    return Timesheet(**values)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


# --- entries as JSONB --------------------------------------------------------------------


def test_days_are_sorted_and_checked_when_set() -> None:
    timesheet = sheet()
    assert [e.work_date for e in timesheet.entries] == [MON, TUE]
    with pytest.raises(ValueError, match="twice"):
        timesheet.entries = [day(MON), day(MON, "2")]
    with pytest.raises(ValueError, match="0-24"):
        check_entries([day(MON, "25")])


def test_days_round_trip_through_json_without_losing_anything() -> None:
    column = EntryList()
    entries = [day(MON, "7.25", is_holiday=True, sheet_holiday=True, note="Diwali"), day(TUE)]
    stored = column.process_bind_param(entries, None)  # type: ignore[arg-type]
    assert stored[0] == {
        "work_date": "2026-10-12",
        "hours": 7.25,
        "is_holiday": True,
        "sheet_holiday": True,
        "double_time_marked": False,
        "note": "Diwali",
    }
    back = column.process_result_value(stored, None)  # type: ignore[arg-type]
    assert back == entries
    assert back[0].hours == Decimal("7.25")


def test_recalculate_replaces_the_days_so_the_change_is_saved() -> None:
    timesheet = Timesheet(flags=[], entries=[day(MON)])
    before = timesheet.entries
    recalculate(timesheet, PayRules(), {MON})
    assert timesheet.entries is not before  # a new list of new days: the column sees it
    assert timesheet.entries[0].is_holiday is True
    assert before[0].is_holiday is False


# --- snapshots ----------------------------------------------------------------------------


def test_a_snapshot_restores_exactly() -> None:
    original = sheet()
    snap = take_snapshot(original)
    assert snap["regular_hours"] == "15.50"  # decimals as text: nothing rounded
    assert snap["entries"][0]["work_date"] == "2026-10-12"

    other = sheet(employee_id=None, extracted_name="X", entries=[], flags=[], week_start=None)
    restore_snapshot(other, snap)
    assert take_snapshot(other) == snap
    assert other.entries == original.entries
    assert other.severity == original.severity is not None  # flags back, severity in step


def test_only_data_changes_count() -> None:
    timesheet = sheet()
    before = take_snapshot(timesheet)
    timesheet.status = TimesheetStatus.APPROVED
    timesheet.reviewed_by_name = "Rita"
    timesheet.notes = "ok"
    assert not data_changed(before, take_snapshot(timesheet))
    timesheet.entries = [day(MON, "9")]
    assert data_changed(before, take_snapshot(timesheet))


def test_save_version_keeps_the_old_data_and_bumps_the_version() -> None:
    session = FakeSession()
    timesheet = sheet()
    before = take_snapshot(timesheet)

    assert save_version(session, timesheet, before, TimesheetChange.RECALCULATED) is None  # type: ignore[arg-type]
    assert timesheet.version == 1 and session.added == []

    timesheet.entries = [day(MON, "4")]
    saved = save_version(
        session,  # type: ignore[arg-type]
        timesheet,
        before,
        TimesheetChange.ENTRIES_EDITED,
        actor_name="Rita",
    )
    assert isinstance(saved, TimesheetVersion)
    assert (saved.version, saved.change, saved.changed_by_name) == (1, "entries_edited", "Rita")
    assert saved.snapshot == before
    assert timesheet.version == 2

    forced = save_version(
        session,  # type: ignore[arg-type]
        timesheet,
        take_snapshot(timesheet),
        TimesheetChange.ROLLED_BACK,
        force=True,
    )
    assert forced is not None and forced.version == 2 and timesheet.version == 3


def test_summary_of_a_version() -> None:
    info = summary(take_snapshot(sheet()))
    assert info["days"] == 2
    assert info["total_hours"] == Decimal("15.50")
    assert info["gross_amount"] == Decimal("6975.00")
    assert info["flags"] == ["long_day"]
    unpriced = take_snapshot(sheet(holiday_amount=None))
    assert summary(unpriced)["gross_amount"] is None
