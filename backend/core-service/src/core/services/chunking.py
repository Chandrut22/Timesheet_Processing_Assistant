"""Chunked extraction: a sheet with many people is cut into pieces of about
CHUNK_PEOPLE people, each piece goes to the AI on its own, and the answers are merged.

Why: one AI answer for 50+ people is long (about 200 tokens a person), slow (it can
pass the AI timeout) and can be cut off at LLM_MAX_OUTPUT_TOKENS; long lists are also
where models skip rows. Smaller pieces avoid all three.

Cutting (split_for_extraction):
  - only when the tables list more than CHUNK_ABOVE_PEOPLE people; smaller documents
    go to the AI whole, exactly as before
  - a person's rows are never split (a one-row-per-day sheet keeps all of a person's
    days in one piece); total rows are left out
  - every piece repeats what the AI needs to read it on its own: the text before the
    first table (client name, week, notes), the table's own heading and header row,
    and small tables without people (e.g. "Client: ... | Week: ...")
  - the order of people is kept, and every person is in exactly one piece

Merging (merge_results): the answers are joined; the same person and week from two
pieces (rare: only when a person is listed in two tables) become one timesheet, with
identical days kept once.

Pure functions, no database and no AI."""

from dataclasses import dataclass

from src.core.services.document_tables import (
    PersonRows,
    Table,
    TableRow,
    norm_code,
    norm_name,
    parse_tables,
    people_in_table,
)
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

PREAMBLE_MAX_CHARS = 3000  # text before the first table, repeated in every piece
CAPTION_LINES = 3  # lines right above a table (sheet name, "Week 1"), kept with it
SMALL_TABLE_CHARS = 1500  # tables without people this small go into every piece
TRAILER_MAX_CHARS = 3000  # other text (notes after the tables) goes into the first piece


@dataclass(frozen=True, slots=True)
class Piece:
    text: str
    people: int


def _caption(lines: list[str], start: int, stop: int) -> tuple[str, list[int]]:
    """Up to CAPTION_LINES non-empty lines just above a table (between `stop` and it),
    and their line numbers."""
    picked = [i for i in range(stop, start) if lines[i].strip()][-CAPTION_LINES:]
    return "\n".join(lines[i][:200] for i in picked), picked


def _table_text(caption: str, table: Table, rows: list[TableRow]) -> str:
    body = "\n".join([table.header_line, table.separator_line, *(r.line for r in rows)])
    return f"{caption}\n{body}" if caption else body


def split_for_extraction(markdown: str, *, people_per_piece: int, above_people: int) -> list[Piece]:
    """The document as one piece (small, or no person column), or as several pieces of
    at most `people_per_piece` people each."""
    lines = markdown.splitlines()
    tables = parse_tables(markdown)
    grouped: list[tuple[Table, str, list[TableRow], list[PersonRows]]] = []
    context_tables: list[str] = []
    caption_lines: set[int] = set()
    stop = 0
    for table in tables:
        # The text above the first table is the preamble, repeated in every piece anyway.
        caption, used = _caption(lines, table.start, stop) if stop else ("", [])
        caption_lines.update(used)
        lead, people = people_in_table(table)
        if people:
            grouped.append((table, caption, lead, people))
        else:
            context_tables.append(_table_text(caption, table, table.rows))
        stop = table.end
    total = sum(len(p) for _, _, _, p in grouped)
    if total <= above_people or people_per_piece < 1:
        return [Piece(markdown, total)]

    first = tables[0].start if tables else len(lines)
    preamble = "\n".join(lines[:first]).strip()[:PREAMBLE_MAX_CHARS]
    shared = [t for t in context_tables if len(t) <= SMALL_TABLE_CHARS]
    once = [t for t in context_tables if len(t) > SMALL_TABLE_CHARS]
    covered = set(range(first)) | caption_lines  # lines used: preamble, captions, tables
    for table in tables:
        covered.update(range(table.start, table.end))
    trailer = "\n".join(ln for i, ln in enumerate(lines) if i not in covered and ln.strip())[
        :TRAILER_MAX_CHARS
    ]

    # Pack people into pieces in reading order, possibly across tables.
    pieces: list[list[tuple[Table, str, list[TableRow], list[PersonRows]]]] = [[]]
    room = people_per_piece
    for table, caption, lead, people in grouped:
        start = 0
        while start < len(people):
            if room == 0:
                pieces.append([])
                room = people_per_piece
            take = people[start : start + room]
            pieces[-1].append((table, caption, lead, take))
            room -= len(take)
            start += len(take)

    out: list[Piece] = []
    for index, parts in enumerate(pieces):
        blocks = [preamble] if preamble else []
        blocks += shared
        if index == 0:
            blocks += once
            if trailer:
                blocks.append(trailer)
        count = 0
        for table, caption, lead, people in parts:
            rows = list(lead) + [row for person in people for row in person.rows]
            blocks.append(_table_text(caption, table, rows))
            count += len(people)
        out.append(Piece("\n\n".join(blocks), count))
    return out


# --- merging -------------------------------------------------------------------------


def _person_key(t: ExtractedTimesheet) -> tuple[str, str]:
    who = (
        f"c:{norm_code(t.employee_code)}"
        if t.employee_code and norm_code(t.employee_code)
        else f"n:{norm_name(t.employee_name or '')}"
    )
    return who, t.week_start.isoformat() if t.week_start else ""


def _day_key(day: ExtractedDay) -> tuple[str, float]:
    when = day.work_date.isoformat() if day.work_date else f"w:{(day.weekday or '').lower()}"
    return when, day.hours


def _merge_two(a: ExtractedTimesheet, b: ExtractedTimesheet) -> ExtractedTimesheet:
    seen = {_day_key(d) for d in a.days}
    days = list(a.days) + [d for d in b.days if _day_key(d) not in seen]
    issues = list(a.issues) + [i for i in b.issues if i not in a.issues]
    stated = a.stated_total
    if a.stated_total is not None and b.stated_total is not None:
        if a.stated_total != b.stated_total:
            issues.append(
                f"Two totals for this person in different parts of the sheet: "
                f"{a.stated_total} and {b.stated_total}"
            )
    elif stated is None:
        stated = b.stated_total
    return a.model_copy(
        update={
            "employee_name": a.employee_name or b.employee_name,
            "employee_code": a.employee_code or b.employee_code,
            "company_name": a.company_name or b.company_name,
            "days": days,
            "stated_total": stated,
            "email_stated_total": a.email_stated_total
            if a.email_stated_total is not None
            else b.email_stated_total,
            "confidence": min(a.confidence, b.confidence),
            "issues": issues,
        }
    )


def merge_results(results: list[ExtractionResult]) -> ExtractionResult:
    """The pieces' answers as one, in order; the same person + week merged."""
    merged: dict[tuple[str, str], ExtractedTimesheet] = {}
    order: list[tuple[str, str]] = []
    for result in results:
        for timesheet in result.timesheets:
            key = _person_key(timesheet)
            if key[0] == "n:":
                key = (f"#{len(order)}", key[1])  # nobody named: never merge it
            if key in merged:
                merged[key] = _merge_two(merged[key], timesheet)
            else:
                merged[key] = timesheet
                order.append(key)
    return ExtractionResult(timesheets=[merged[k] for k in order])
