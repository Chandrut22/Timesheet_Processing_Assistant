"""Long documents: overlapping pieces (split_with_overlap) and the combining of the
answers (merge_results, combine_by). Pure functions: no database, no AI."""

from datetime import date

import pytest

from src.core.services.chunking import (
    OVERLAP_FLAG,
    Combined,
    Split,
    combine_by,
    merge_results,
    split_with_overlap,
)
from src.core.services.document_tables import count_people
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TITLE = "# ABC Staffing - week of 2026-06-01"


def grid(n: int) -> str:
    """A weekly grid with n people, the way Docling writes an Excel sheet."""
    lines = [TITLE, "", "| Emp ID | Employee Name | " + " | ".join(DAYS) + " | Total |"]
    lines.append("|" + "---|" * (len(DAYS) + 3))
    lines += [f"| E{i:03d} | Person {i:03d} | 8 | 8 | 8 | 8 | 8 | 40 |" for i in range(1, n + 1)]
    lines += [f"| Total | | | | | | | {40 * n} |", "", "Notes: OT approved for Person 010."]
    return "\n".join(lines)


def monthly(people: int, days: int = 31) -> str:
    """One row per person per day for a month, the name only on each person's first row."""
    lines = ["| Name | Date | Hours | Notes |", "| --- | --- | --- | --- |"]
    for i in range(people):
        for d in range(days):
            name = f"Person {i:02d}" if d == 0 else ""
            lines.append(f"| {name} | 2026-07-{d + 1:02d} | 8 | regular shift at client site {i} |")
    return "\n".join(lines)


def blocks(people: int) -> str:
    """Free text / a vision transcription: one block per person, no tables."""
    return "\n\n".join(
        f"Employee: Person {i}\nMonday 8 hours, Tuesday 8 hours, Wednesday 7.5 hours on the "
        "north site; Thursday 8 hours; Friday off (doctor)."
        for i in range(people)
    )


def split(text: str, **kw: int) -> Split:
    options = {"target": 12_000, "overlap": 1_500, "max_parts": 40, "max_people": 15} | kw
    return split_with_overlap(
        text,
        target=options["target"],
        overlap=options["overlap"],
        max_parts=options["max_parts"],
        max_people=options["max_people"],
    )


def covered(text: str, s: Split) -> set[int]:
    lines: set[int] = set()
    for piece in s.pieces:
        lines |= set(range(piece.first_line, piece.end_line))
    return lines


# --- cutting ---------------------------------------------------------------------------


def test_a_short_document_is_one_piece_unchanged() -> None:
    text = grid(10)
    (piece,) = split(text).pieces
    assert piece.text == text and piece.overlap_chars == 0


@pytest.mark.parametrize(
    "text", [grid(60), grid(400), monthly(15), blocks(120)], ids=["60", "400", "monthly", "text"]
)
def test_every_line_is_read_and_no_piece_is_too_big(text: str) -> None:
    s = split(text)
    assert len(s.pieces) > 1 and not s.capped
    assert covered(text, s) == set(range(len(text.split("\n"))))
    assert all(len(p.text) <= 12_000 for p in s.pieces)
    assert s.read_chars == len(text)


def test_pieces_overlap_the_one_before() -> None:
    s = split(grid(60))
    for before, after in zip(s.pieces, s.pieces[1:], strict=False):
        assert after.first_line < before.end_line  # starts inside the previous piece
        assert after.overlap_chars > 0
        assert after.end_line > before.end_line  # and always moves on


def test_never_cut_inside_a_line() -> None:
    text = monthly(15)
    lines = set(text.split("\n"))
    for piece in split(text).pieces:
        assert all(line in lines for line in piece.text.split("\n") if line.strip())


def test_a_piece_inside_a_table_repeats_the_title_and_header() -> None:
    for piece in split(grid(60)).pieces:
        assert piece.text.startswith(TITLE)
        assert piece.text.count(TITLE) == 1
        assert "| Emp ID | Employee Name |" in piece.text
        assert count_people(piece.text) is not None  # header right above its rows


def test_at_most_chunk_people_new_people_per_piece() -> None:
    s = split(grid(60))
    assert max(p.people for p in s.pieces) <= 15 + 4  # 15 new + a few repeated from before
    assert s.pieces[0].people == 15


def test_a_monthly_sheet_keeps_whole_people_together_where_it_can() -> None:
    s = split(monthly(15))
    for piece in s.pieces[1:]:
        first_row = next(
            ln
            for ln in piece.text.split("\n")
            if ln.startswith("| ") and "---" not in ln and "Name" not in ln
        )
        assert first_row  # starts on a row, never on half a line


def test_free_text_is_cut_between_person_blocks() -> None:
    for piece in split(blocks(120)).pieces[1:]:
        body = piece.text.lstrip()
        assert body.startswith("Employee:") or body.startswith("Monday")


def test_too_many_parts_stops_and_says_where() -> None:
    s = split(grid(400), max_parts=5)
    assert len(s.pieces) == 5 and s.capped
    assert s.stopped_at_line is not None and s.read_chars < s.total_chars


def test_one_huge_line_is_a_piece_of_its_own() -> None:
    text = "intro\n" + "x" * 30_000 + "\nend"
    s = split(text)
    assert any(len(p.text) > 12_000 for p in s.pieces)  # caller flags document_truncated
    assert covered(text, s) == {0, 1, 2}


# --- combining -------------------------------------------------------------------------


def sheet(
    code: str | None, name: str | None, days: list[tuple[int, float]], week: date | None = None
) -> ExtractedTimesheet:
    return ExtractedTimesheet(
        employee_code=code,
        employee_name=name,
        week_start=week,
        days=[ExtractedDay(work_date=date(2026, 6, d), hours=h) for d, h in days],
        confidence=0.95,
    )


def parts(*answers: list[ExtractedTimesheet]) -> list[ExtractionResult]:
    return [ExtractionResult(timesheets=list(a)) for a in answers]


def test_answers_are_joined_in_order() -> None:
    c = merge_results(parts([sheet("E001", "A", [(1, 8)])], [sheet("E002", "B", [(1, 8)])]))
    assert [t.employee_code for t in c.result.timesheets] == ["E001", "E002"]
    assert c.joined == 0


def test_a_person_seen_twice_in_the_overlap_becomes_one_with_no_doubled_days() -> None:
    week = date(2026, 6, 1)
    a = sheet("E001", "Grace", [(1, 8), (2, 8), (3, 8)], week)
    b = sheet("e-001", "Grace", [(3, 8), (4, 8), (5, 8)], week).model_copy(
        update={"confidence": 0.7, "stated_total": 40.0}
    )
    c = merge_results(parts([a], [b]))
    (one,) = c.result.timesheets
    assert [d.work_date.day for d in one.days if d.work_date] == [1, 2, 3, 4, 5]
    assert one.confidence == 0.7 and one.stated_total == 40.0
    assert c.parts == [frozenset({1, 2})] and c.joined == 1
    assert c.flags == [[]]  # no disagreement


def test_a_disagreement_keeps_the_later_part_and_flags_it() -> None:
    a = sheet("E001", "Grace", [(1, 8), (2, 8)])
    b = sheet("E001", "Grace", [(2, 9), (3, 8)])
    c = merge_results(parts([a], [b]))
    (one,) = c.result.timesheets
    assert {(d.work_date.day, d.hours) for d in one.days if d.work_date} == {(1, 8), (2, 9), (3, 8)}
    (flag,) = c.flags[0]
    assert flag["code"] == OVERLAP_FLAG
    assert "8 h in part 1, 9 h in part 2 (kept 9 h)" in flag["message"]
    assert c.disagreements and c.disagreements[0].startswith("Grace")


def test_two_rows_in_the_same_part_are_never_joined() -> None:
    a = sheet("E001", "Grace", [(1, 8)])
    c = merge_results(parts([a, a]))
    assert len(c.result.timesheets) == 2  # left for the duplicate rules


def test_different_weeks_and_unnamed_timesheets_stay_apart() -> None:
    a = sheet("E001", "Grace", [(1, 8)], date(2026, 6, 1))
    b = sheet("E001", "Grace", [(8, 8)], date(2026, 6, 8))
    assert len(merge_results(parts([a], [b])).result.timesheets) == 2
    nobody = sheet(None, None, [(1, 8)])
    assert len(merge_results(parts([nobody], [nobody])).result.timesheets) == 2


def test_after_matching_the_same_employee_written_differently_becomes_one() -> None:
    week = date(2026, 6, 1)
    c = merge_results(
        parts(
            [sheet("E001", "R. Kumar", [(1, 8), (2, 8)], week)],
            [sheet(None, "Rahul Kumar", [(3, 8), (4, 8)], week), sheet("E9", "Other", [(1, 8)])],
        )
    )
    assert len(c.result.timesheets) == 3  # different keys before matching
    again = combine_by(c, [("co", "emp-1", "2026-06-01"), ("co", "emp-1", "2026-06-01"), None])
    assert len(again.result.timesheets) == 2
    rahul = again.result.timesheets[0]
    assert len(rahul.days) == 4 and rahul.employee_code == "E001"
    assert again.parts[0] == frozenset({1, 2})


def test_combine_by_never_joins_timesheets_from_the_same_part() -> None:
    c = Combined.of(
        ExtractionResult(timesheets=[sheet("E1", "A", [(1, 8)]), sheet("E1", "A", [(1, 8)])])
    )
    assert len(combine_by(c, ["k", "k"]).result.timesheets) == 2


def test_an_overlap_flag_survives_the_second_combine() -> None:
    a = sheet("E001", "Grace", [(1, 8)])
    b = sheet("E001", "Grace", [(1, 9)])
    c = merge_results(parts([a], [b]))
    again = combine_by(c, [("co", "e", "")])
    assert [f["code"] for f in again.flags[0]] == [OVERLAP_FLAG]
