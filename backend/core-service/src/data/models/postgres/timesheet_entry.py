"""The days of a timesheet, stored as a JSONB array on timesheets.entries.

A timesheet always has 0-7 days and they are only ever read or written with their
timesheet, so they live on the timesheet row instead of in a table of their own:

    [{"work_date": "2026-10-12", "hours": 8.0, "is_holiday": false,
      "sheet_holiday": false, "double_time_marked": false, "note": null}, ...]

In Python each day is a TimesheetEntry (a plain dataclass, not a table). The column
type (EntryList) checks and orders the days on the way in: one entry per date, hours
0-24, sorted by date. To change days, assign a new list (timesheet.entries = [...]);
list operations (append, clear, ...) are tracked too. Changing a field of a day that
is already saved is NOT seen by the database: build a new entry
(dataclasses.replace)."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

HOURS_STEP = Decimal("0.01")
MAX_HOURS = Decimal("24")
NOTE_MAX = 255


@dataclass(slots=True)
class TimesheetEntry:
    """One day on a timesheet."""

    work_date: date
    hours: Decimal
    # Holiday in the end (marked on the sheet / by a reviewer, OR in the holiday
    # calendar). Recomputed by pay_rules.recalculate(); never set it directly.
    is_holiday: bool = False
    # Marked as a holiday on the sheet itself, or by a reviewer. Kept apart from the
    # calendar so deleting a calendar holiday really removes it from the timesheet.
    sheet_holiday: bool = False
    double_time_marked: bool = False
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["work_date"] = self.work_date.isoformat()
        data["hours"] = float(self.hours)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TimesheetEntry":
        return cls(
            work_date=date.fromisoformat(str(data["work_date"])),
            hours=Decimal(str(data["hours"])).quantize(HOURS_STEP),
            is_holiday=bool(data.get("is_holiday", False)),
            sheet_holiday=bool(data.get("sheet_holiday", False)),
            double_time_marked=bool(data.get("double_time_marked", False)),
            note=data.get("note"),
        )


def check_entries(entries: list[TimesheetEntry]) -> list[TimesheetEntry]:
    """Sorted by date; raises ValueError on a repeated date or hours outside 0-24."""
    seen: set[date] = set()
    for entry in entries:
        if entry.work_date in seen:
            raise ValueError(f"{entry.work_date} appears twice on the timesheet.")
        seen.add(entry.work_date)
        if not (Decimal("0") <= Decimal(entry.hours) <= MAX_HOURS):
            raise ValueError(f"{entry.work_date}: {entry.hours} h is outside 0-24.")
        if entry.note is not None and len(entry.note) > NOTE_MAX:
            raise ValueError(
                f"{entry.work_date}: the note is longer than {NOTE_MAX} characters."
            )
    return sorted(entries, key=lambda e: e.work_date)


class EntryList(TypeDecorator[list[TimesheetEntry]]):
    """JSONB <-> list[TimesheetEntry], checked and sorted on every write."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(
        self, value: list[TimesheetEntry] | None, dialect: Dialect
    ) -> list[dict[str, Any]]:
        return [e.to_json() for e in check_entries(list(value or []))]

    def process_result_value(
        self, value: list[dict[str, Any]] | None, dialect: Dialect
    ) -> list[TimesheetEntry]:
        return [TimesheetEntry.from_json(item) for item in value or []]

    def compare_values(self, x: Any, y: Any) -> bool:
        def plain(v: Any) -> Any:
            return [e.to_json() for e in v] if isinstance(v, list) else v

        return bool(plain(x) == plain(y))
