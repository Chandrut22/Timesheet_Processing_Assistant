"""Long documents: cut into overlapping pieces, one AI call per piece, answers combined.

Why: the AI reads at most LLM_MAX_INPUT_CHARS, one long answer is slow and can be cut
off at LLM_MAX_OUTPUT_TOKENS, and long lists are where models skip rows. Any document
longer than CHUNK_TARGET_CHARS (or listing more than CHUNK_PEOPLE people) is therefore
read in pieces: tables, free text, vision transcriptions and email bodies alike.

Cutting (split_with_overlap):
  - a piece is at most CHUNK_TARGET_CHARS and holds at most CHUNK_PEOPLE new people
    (each person costs about 200 tokens of answer); the text is never cut inside a line
  - near the end of a piece the best place to cut wins: a blank line, heading or page
    break ("--- page 3 ---" from the vision reader), the
    end of a table, the start of a person block ("Employee: ..."), a row that starts a
    new person, any table row, any line
  - each piece starts about CHUNK_OVERLAP_CHARS before the previous one ended, so a
    person whose rows straddle a cut is seen whole in one of the two pieces, and a name
    line is never separated from the hours under it
  - every piece can be read on its own: the text before the first table (client, week)
    and, when a piece starts inside a table, that table's header row are put on top
  - at most CHUNK_MAX_PARTS pieces; the rest of a longer document is not read and the
    caller flags it (document_too_large), never a silent cut

Combining (merge_results, combine_by):
  - the same person (employee code, else name) and week found in different parts
    becomes one timesheet; a day read in both parts (the overlap) is kept once
  - the same day with different hours in two parts: the later part's value is kept
    (it read the row with the table header and the rows after it) and the timesheet
    gets an overlap_disagreement flag, so a person checks it
  - timesheets from the SAME part are never joined (two rows for one person in one
    part are a real duplicate, left for the duplicate rules)
  - combine_by() repeats this with a key from employee matching ("R. Kumar" in one part,
    "Rahul Kumar" in the next, both matched to the same employee)

Pure functions, no database and no AI."""

import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.core.services.document_tables import (
    Table,
    count_people,
    norm_code,
    norm_name,
    parse_tables,
)
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

PREAMBLE_MAX_CHARS = 3000  # text before the first table, repeated in every piece
OVERLAP_FLAG = "overlap_disagreement"
# Cut only in the last part of a piece (a piece is never much shorter than the target).
CUT_WINDOW = 0.4
# "--- page 3 ---": where the vision reader joined two pages.
_PAGE_BREAK = re.compile(r"^-{3}\s*page\s+\d+\s*-{3}$", re.IGNORECASE)
# "Employee: Rahul Kumar", "| Employee Name | Rahul |", "Name - Grace": a person block.
_PERSON_BLOCK = re.compile(
    r"^\s*\|?\s*(employee|emp|staff|worker|associate|name)\b[^|:\n]{0,30}[:|-]", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Piece:
    text: str
    people: int = 0  # people in this piece's tables (0 = unknown / no table)
    first_line: int = 0  # 0-based line range of the document in this piece (end exclusive)
    end_line: int = 0
    overlap_chars: int = 0  # characters repeated from the previous piece


@dataclass(frozen=True, slots=True)
class Split:
    pieces: list[Piece]
    total_chars: int
    read_chars: int  # characters of the document in some piece
    stopped_at_line: int | None = None  # 1-based line where reading stopped (CHUNK_MAX_PARTS)

    @property
    def capped(self) -> bool:
        return self.stopped_at_line is not None


def _people(text: str) -> int:
    found = count_people(text)
    return found.total if found is not None else 0


def single_piece(text: str) -> Split:
    lines = text.count("\n") + 1
    return Split([Piece(text, _people(text), 0, lines, 0)], len(text), len(text))


def _cut_scores(lines: list[str], tables: list[Table]) -> tuple[list[int], list[bool]]:
    """(score, starts_person): score[i] = how good it is to end a piece just before
    line i (0 = never); starts_person[i] = line i starts a new person (a table row with
    a name / code, or a person block)."""
    n = len(lines)
    score = [1] * (n + 1)
    starts = [False] * n
    for table in tables:
        # rows after the header: cutting between rows is fine, a new person is better
        person_cols = [c for c in (table.name_col, table.code_col) if c is not None]
        for i in range(table.start + 2, table.end):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            new_person = any(c < len(cells) and cells[c] for c in person_cols)
            starts[i] = new_person
            score[i] = 3 if new_person else 2
        # never between the header, the separator and the first row
        for i in (table.start + 1, table.start + 2):
            if i <= n:
                score[i] = 0
        if table.end <= n:
            score[table.end] = max(score[table.end], 5)
    for i in range(1, n):
        line, prev = lines[i].strip(), lines[i - 1].strip()
        if score[i] == 0:
            continue
        if not line or not prev or line.startswith("#") or _PAGE_BREAK.match(line):
            score[i] = max(score[i], 6)
        elif _PERSON_BLOCK.match(line):
            score[i] = max(score[i], 4)
    in_people_table = {
        i for table in tables if table.has_person_column for i in range(table.start, table.end)
    }
    for i in range(n):  # "Employee: ..." / "| Employee Name | Rahul |" outside a people table
        if i not in in_people_table and _PERSON_BLOCK.match(lines[i].strip()):
            starts[i] = True
    score[0] = 0
    return score, starts


def _table_at(tables: list[Table], line: int) -> Table | None:
    """The table whose rows (not its header) contain this line."""
    for table in tables:
        if table.start + 2 <= line < table.end:
            return table
    return None


def split_with_overlap(
    text: str, *, target: int, overlap: int, max_parts: int, max_people: int = 0
) -> Split:
    """The document as one piece (short), or as overlapping pieces of at most `target`
    characters and at most `max_people` new people each (0 = no people limit; see the
    module docstring)."""
    people_total = _people(text)
    if target < 1 or (len(text) <= target and (not max_people or people_total <= max_people)):
        return single_piece(text)
    lines = text.split("\n")
    n = len(lines)
    size = [len(line) + 1 for line in lines]
    tables = parse_tables(text)
    # starts_person: the people limit keeps each AI answer short (about 200 tokens a person)
    score, starts_person = _cut_scores(lines, tables)
    first_table = tables[0].start if tables else None
    preamble = "\n".join(lines[:first_table]).strip()[:PREAMBLE_MAX_CHARS] if first_table else ""

    def context(start: int) -> str:
        out = ""
        if preamble and first_table is not None and start >= first_table:
            out = preamble + "\n\n"
        table = _table_at(tables, start)
        if table is not None:  # directly above the rows, so they stay one table
            out += f"{table.header_line}\n{table.separator_line}\n"
        return out

    pieces: list[Piece] = []
    # start: first line of the piece (with the overlap); new_start: its first new line
    start = new_start = 0
    stopped: int | None = None
    while new_start < n:
        if len(pieces) == max_parts:
            stopped = new_start + 1
            break
        ctx = context(start)
        lead = sum(size[start:new_start])
        room = max(target - len(ctx) - lead, target // 4)
        end, used, people = new_start, 0, 0
        while end < n and used + size[end] <= room:
            if starts_person[end]:
                if max_people and people >= max_people and end > new_start:
                    break
                people += 1
            used += size[end]
            end += 1
        if end == new_start:
            end = new_start + 1  # one line longer than a piece: on its own
        elif end < n:
            low = new_start + max(1, int((end - new_start) * (1 - CUT_WINDOW)))
            best = max(range(low, end + 1), key=lambda i: (score[i], i))
            if score[best] > 0:
                end = best
        body = "\n".join(lines[start:end]).strip("\n")
        piece_text = ctx + body
        pieces.append(Piece(piece_text, _people(piece_text), start, end, lead if pieces else 0))
        if end >= n:
            break
        # The next piece starts about `overlap` characters earlier, but never more than a
        # quarter of this piece's new text (small pieces would otherwise repeat entirely).
        limit = min(overlap, sum(size[new_start:end]) // 4)
        back, acc = end, 0
        while back - 1 > start and acc + size[back - 1] <= limit:
            back -= 1
            acc += size[back]
        table = next((t for t in tables if t.start < back <= t.start + 2), None)
        if table is not None:
            back = table.start  # never start between a header and its first row
        start, new_start = max(back, start + 1), end
    read_lines = pieces[-1].end_line if pieces else 0
    read_chars = min(len(text), sum(size[:read_lines]))
    return Split(pieces, len(text), read_chars, stopped)


# --- combining -------------------------------------------------------------------------


def _person_key(t: ExtractedTimesheet) -> tuple[str, str] | None:
    """(who, week); None = nobody named: never joined."""
    if t.employee_code and norm_code(t.employee_code):
        who = f"c:{norm_code(t.employee_code)}"
    elif t.employee_name and norm_name(t.employee_name):
        who = f"n:{norm_name(t.employee_name)}"
    else:
        return None
    return who, t.week_start.isoformat() if t.week_start else ""


def _day_key(day: ExtractedDay) -> str:
    return day.work_date.isoformat() if day.work_date else f"w:{(day.weekday or '').lower()}"


def _day_label(day: ExtractedDay) -> str:
    return day.work_date.strftime("%d %b %Y") if day.work_date else (day.weekday or "a day")


@dataclass(slots=True)
class Entry:
    timesheet: ExtractedTimesheet
    parts: set[int]
    disagreements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Combined:
    """The combined answer, and per timesheet: the parts it came from and extra flags."""

    result: ExtractionResult
    parts: list[frozenset[int]]
    flags: list[list[dict[str, Any]]]
    joined: int = 0  # timesheets found in more than one part
    disagreements: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, result: ExtractionResult, part: int = 1) -> "Combined":
        n = len(result.timesheets)
        return cls(result, [frozenset({part})] * n, [[] for _ in range(n)])


def _join(entry: Entry, other: ExtractedTimesheet, other_parts: set[int]) -> None:
    """Add a timesheet from later part(s) to an entry (in place)."""
    a, b = entry.timesheet, other
    later = max(other_parts)
    earlier = max(entry.parts)
    days = list(a.days)
    seen: dict[str, list[int]] = {}
    for index, day in enumerate(days):
        seen.setdefault(_day_key(day), []).append(index)
    for day in b.days:
        key = _day_key(day)
        same = seen.get(key)
        if not same:
            days.append(day)  # a new day (or a real second row in the later part)
            continue
        if any(days[i].hours == day.hours for i in same):
            continue  # read twice in the overlap: kept once
        old = days[same[0]]
        days[same[0]] = day  # the later part read it with the header and the rows after it
        entry.disagreements.append(
            f"{_day_label(day)}: {old.hours:g} h in part {earlier}, {day.hours:g} h in "
            f"part {later} (kept {day.hours:g} h)"
        )
    issues = list(a.issues) + [i for i in b.issues if i not in a.issues]
    stated = a.stated_total
    if a.stated_total is not None and b.stated_total is not None:
        if a.stated_total != b.stated_total:
            issues.append(
                f"Two totals for this person in different parts of the document: "
                f"{a.stated_total} and {b.stated_total}"
            )
    elif stated is None:
        stated = b.stated_total
    unreadable = list(a.unreadable_days) + [
        d for d in b.unreadable_days if d not in a.unreadable_days
    ]
    entry.timesheet = a.model_copy(
        update={
            "employee_name": a.employee_name or b.employee_name,
            "employee_code": a.employee_code or b.employee_code,
            "company_name": a.company_name or b.company_name,
            "week_start": a.week_start or b.week_start,
            "days": days,
            "stated_total": stated,
            "email_stated_total": a.email_stated_total
            if a.email_stated_total is not None
            else b.email_stated_total,
            "unreadable_days": unreadable,
            "confidence": min(a.confidence, b.confidence),
            "issues": issues,
        }
    )
    entry.parts |= other_parts


# (join key, timesheet, parts it came from, extra flags)
_Item = tuple[Hashable | None, ExtractedTimesheet, set[int], list[dict[str, Any]]]


def _overlap_flag(disagreements: list[str]) -> dict[str, Any]:
    return {
        "code": OVERLAP_FLAG,
        "message": "This long document was read in overlapping parts, and two parts read "
        "different hours: " + "; ".join(disagreements) + ". Check the original.",
        "days": disagreements,
    }


def _combine(items: Sequence[_Item]) -> Combined:
    """Join items with the same key whose parts do not overlap, in order."""
    entries: list[tuple[Entry, list[dict[str, Any]]]] = []
    by_key: dict[Hashable, int] = {}
    joined: set[int] = set()
    for key, timesheet, parts, flags in items:
        index = by_key.get(key) if key is not None else None
        if index is not None and not (entries[index][0].parts & parts):
            _join(entries[index][0], timesheet, parts)
            for flag in flags:
                if flag.get("code") == OVERLAP_FLAG:
                    entries[index][0].disagreements.extend(flag.get("days") or [])
                else:
                    entries[index][1].append(flag)
            joined.add(index)
            continue
        entry = Entry(timesheet, set(parts))
        for flag in flags:  # an overlap flag from an earlier combine: keep its days
            if flag.get("code") == OVERLAP_FLAG:
                entry.disagreements.extend(flag.get("days") or [])
        entries.append((entry, [f for f in flags if f.get("code") != OVERLAP_FLAG]))
        if key is not None and key not in by_key:
            by_key[key] = len(entries) - 1
    all_disagreements: list[str] = []
    flags_out: list[list[dict[str, Any]]] = []
    for entry, flags in entries:
        extra = list(flags)
        if entry.disagreements:
            extra.append(_overlap_flag(entry.disagreements))
            who = entry.timesheet.employee_name or entry.timesheet.employee_code or "?"
            all_disagreements += [f"{who}, {d}" for d in entry.disagreements]
        flags_out.append(extra)
    return Combined(
        ExtractionResult(timesheets=[e.timesheet for e, _ in entries]),
        [frozenset(e.parts) for e, _ in entries],
        flags_out,
        joined=len(joined),
        disagreements=all_disagreements,
    )


def merge_results(results: list[ExtractionResult]) -> Combined:
    """The parts' answers (in part order, part 1 first) as one: the same person + week
    from different parts joined, days read twice in the overlap kept once."""
    items: list[_Item] = [
        (_person_key(t), t, {part}, [])
        for part, result in enumerate(results, start=1)
        for t in result.timesheets
    ]
    return _combine(items)


def combine_by(combined: Combined, keys: Sequence[Hashable | None]) -> Combined:
    """Join again with keys from employee matching (one per timesheet; None = never):
    the same employee and week written differently in two parts becomes one."""
    items = [
        (key, t, set(parts), list(flags))
        for key, t, parts, flags in zip(
            keys, combined.result.timesheets, combined.parts, combined.flags, strict=True
        )
    ]
    again = _combine(items)
    again.joined += combined.joined
    return again
