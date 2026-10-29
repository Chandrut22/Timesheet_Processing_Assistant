"""Big sheets (about 50 people): the people count that catches skipped rows (the
cutting into pieces and the combining are tested in test_chunking.py)."""

import pytest

from src.core.services.document_tables import (
    count_people,
    missing_rows_flag,
    norm_code,
    norm_name,
    parse_tables,
)

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def grid(
    n: int, *, title: str = "# ABC Staffing - week of 2026-06-01", total: bool = True
) -> str:
    """A weekly grid with n people, the way Docling writes an Excel sheet."""
    lines = [title, "", "| Emp ID | Employee Name | " + " | ".join(DAYS) + " | Total |"]
    lines.append("|" + "---|" * (len(DAYS) + 3))
    for i in range(1, n + 1):
        lines.append(f"| E{i:03d} | Person {i:03d} | 8 | 8 | 8 | 8 | 8 | 40 |")
    if total:
        lines.append(f"| Total | | | | | | | {40 * n} |")
    return "\n".join(lines)


def per_day(people: int) -> str:
    """One row per person per day, the name only on each person's first row."""
    lines = ["| Name | Date | Hours |", "| --- | --- | --- |"]
    for i in range(1, people + 1):
        for d in range(5):
            name = f"Person {i}" if d == 0 else ""
            lines.append(f"| {name} | 2026-06-0{d + 1} | 8 |")
    return "\n".join(lines)


# --- the people count ---------------------------------------------------------------


def test_finds_the_person_columns() -> None:
    (table,) = parse_tables(grid(3))
    assert (table.code_col, table.name_col) == (0, 1)


def test_counts_people_and_ignores_the_total_row() -> None:
    count = count_people(grid(50))
    assert count is not None and count.total == 50


def test_one_row_per_day_counts_each_person_once() -> None:
    count = count_people(per_day(12))
    assert count is not None and count.total == 12


def test_no_table_means_unknown() -> None:
    assert count_people("Grace worked 8 hours Monday to Friday.") is None


def test_a_table_without_a_person_column_means_unknown() -> None:
    assert count_people("| Day | Hours |\n| --- | --- |\n| Mon | 8 |") is None


def test_other_name_columns_are_not_people() -> None:
    text = (
        "| Company Name | Project Code | Hours |\n| --- | --- | --- |\n| ABC | P1 | 8 |"
    )
    assert count_people(text) is None


def test_a_name_with_no_hours_is_not_counted() -> None:
    text = "| Name | Mon | Tue |\n| --- | --- | --- |\n| Grace | 8 | 8 |\n| Ravi | | |"
    count = count_people(text)
    assert count is not None and count.total == 1


def test_all_found_by_code_or_by_name() -> None:
    count = count_people(grid(3))
    assert count is not None
    found = [("E001", None), (None, "person 002"), ("e-003", "Someone Else")]
    assert count.missing(found) == []


def test_missing_people_are_named_in_the_flag() -> None:
    count = count_people(grid(50))
    assert count is not None
    found = [(f"E{i:03d}", None) for i in range(1, 51) if i not in (12, 31, 44)]
    missing = count.missing(found)
    assert [p.code for p in missing] == ["E012", "E031", "E044"]
    flag = missing_rows_flag(count, missing)
    assert flag["code"] == "possible_missing_rows"
    assert "lists 50 people; 47 were extracted" in str(flag["message"])
    assert "Person 012 (E012)" in str(flag["message"])


def test_long_missing_lists_are_shortened() -> None:
    count = count_people(grid(30))
    assert count is not None
    flag = missing_rows_flag(count, count.missing([]))
    assert "and 20 more" in str(flag["message"]) and len(flag["missing"]) == 30  # type: ignore[arg-type]


def test_the_same_person_on_two_sheets_counts_once() -> None:
    text = grid(3, title="## Week 1", total=False) + "\n\n" + grid(3, title="## Week 2")
    count = count_people(text)
    assert count is not None and count.total == 3


@pytest.mark.parametrize(("raw", "code"), [("e-001", "E001"), (" E 001 ", "E001")])
def test_code_normalising(raw: str, code: str) -> None:
    assert norm_code(raw) == code


def test_name_normalising_ignores_order_and_case() -> None:
    assert norm_name("Kumar, Robert") == norm_name("robert  KUMAR")


# --- found in the first batch run: single-person sheets -------------------------------

ONE_PERSON_XLSX = """| ABC Staffing Solutions Pvt Ltd |
|--------------------------------|
| Weekly Timesheet               |

| Employee Name   | Rahul Kumar   |
|-----------------|---------------|
| Employee ID     | SYN-EMP-001   |
| Week Ending     | 2026-10-11    |

| Date       | Day       |   Hours |
|------------|-----------|---------|
| 2026-10-05 | Monday    |       8 |
| 2026-10-06 | Tuesday   |       8 |
| Total      |           |      16 |"""


def test_a_label_value_block_is_not_a_people_table() -> None:
    # Docling writes "Employee Name | Rahul Kumar" (with ID and week below) as a small
    # table; "Employee ID" and "Week Ending" are labels, not two missing people.
    assert count_people(ONE_PERSON_XLSX) is None


def test_label_rows_inside_a_people_table_are_skipped() -> None:
    text = (
        "| Employee Name | Mon | Tue |\n| --- | --- | --- |\n| Week ending: | "
        "2026-10-11 | |\n| Grace Okoye | 8 | 8 |\n| Notes | leave 12 Oct | |"
    )
    count = count_people(text)
    assert count is not None and [p.name for p in count.people] == ["Grace Okoye"]


def test_a_csv_with_date_and_hours_columns_is_one_person() -> None:
    text = (
        "| Employee ID | Employee Name | Date | Hours |\n| --- | --- | --- | --- |\n"
        + "\n".join(
            f"| SYN-EMP-016 | Hannah Weiss | 2026-10-0{d} | 7.5 |" for d in range(5, 10)
        )
    )
    count = count_people(text)
    assert count is not None and count.total == 1


def test_a_crew_sheet_with_dated_day_columns_still_counts() -> None:
    text = (
        "| Emp ID | Employee Name | Mon 12-Oct | Tue 13-Oct | Total |\n| --- | --- | "
        "--- | --- | --- |\n| SYN-EMP-007 | Ravi Kumar | 8 | 8 | 16 |\n| SYN-EMP-008 | "
        "Aisha Rahman | 8 | 8 | 16 |"
    )
    count = count_people(text)
    assert count is not None and count.total == 2
