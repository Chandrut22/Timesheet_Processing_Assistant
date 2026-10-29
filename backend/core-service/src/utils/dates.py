from datetime import date, timedelta

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


_DAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def weekday_name(index: int) -> str:
    """0 -> 'Monday' (the company's week_start numbering)."""
    return _DAY_NAMES[index % 7]


def weekday_index(name: str | None) -> int | None:
    """'Mon', 'monday', 'MON.' -> 0. Unknown -> None."""
    if not name:
        return None
    return _WEEKDAYS.get(name.strip().lower()[:3])


def start_of_week(day: date, week_start: int = 0) -> date:
    """The first day of day's week; week_start 0 = Monday ... 6 = Sunday."""
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def date_in_week(week_first_day: date, weekday: int) -> date:
    """The date of `weekday` in the week that starts on week_first_day."""
    return week_first_day + timedelta(days=(weekday - week_first_day.weekday()) % 7)
