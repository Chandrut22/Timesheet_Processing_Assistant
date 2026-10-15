"""How serious each flag is, as the use case defines it.

    high   = the hours could be wrong, or paid to the wrong person / twice
    medium = a pay code or master-data question a reviewer should confirm
    low    = an assumption the system made, worth a glance

Severity is added to every flag automatically when a timesheet's flags are set
(see Timesheet._set_severity), so the code that raises a flag never has to know it."""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


FLAG_SEVERITY: dict[str, Severity] = {
    # realistic hours / totals
    "long_day": Severity.HIGH,
    "day_over_24": Severity.HIGH,
    "total_mismatch": Severity.HIGH,
    "conflicting_hours": Severity.HIGH,
    "no_entries": Severity.HIGH,
    "duplicate_day": Severity.HIGH,
    # paid twice / to the wrong person
    "duplicate_week": Severity.HIGH,
    "duplicate_file": Severity.HIGH,
    "employee_unmatched": Severity.HIGH,
    "no_company": Severity.HIGH,
    # pay codes and master data
    "holiday_worked": Severity.MEDIUM,
    "holiday_not_in_calendar": Severity.MEDIUM,
    "outside_assignment": Severity.MEDIUM,
    "name_mismatch": Severity.MEDIUM,
    "unknown_code": Severity.MEDIUM,
    "undated_days": Severity.MEDIUM,
    "model_issue": Severity.MEDIUM,
    "default_rules": Severity.MEDIUM,
    # assumptions
    "dates_assumed": Severity.LOW,
}

DEFAULT_SEVERITY = Severity.MEDIUM  # a new flag code nobody mapped yet

SEVERITY_RANK: dict[str, int] = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


def severity_of(code: str | None) -> Severity:
    return FLAG_SEVERITY.get(code or "", DEFAULT_SEVERITY)


def with_severity(flags: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Copy of the flags with "severity" filled in from the code (an explicit one is kept)."""
    result: list[dict[str, Any]] = []
    for flag in flags:
        item = dict(flag)
        item["severity"] = item.get("severity") or severity_of(item.get("code")).value
        result.append(item)
    return result


def highest_severity(flags: Iterable[Mapping[str, Any]]) -> str | None:
    """The worst severity among the flags, or None when there are none."""
    best: str | None = None
    for flag in flags:
        level = str(flag.get("severity") or severity_of(flag.get("code")).value)
        if best is None or SEVERITY_RANK.get(level, 0) > SEVERITY_RANK.get(best, 0):
            best = level
    return best
