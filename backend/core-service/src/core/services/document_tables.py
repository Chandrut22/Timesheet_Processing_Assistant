"""Find the people in a document's tables, without the AI.

Docling turns Excel, CSV, Word and most PDFs into Markdown, with each table written as

    | Name | Emp ID | Mon | Tue | ... |
    |------|--------|-----|-----|-----|
    | Grace Okoye | E001 | 8 | 8 | ... |

This module reads those tables and finds the column that names the person (a name or
an employee code column). Two uses:

  - the people count: how many people the sheet lists, to catch the AI silently
    skipping rows (flag possible_missing_rows)
  - chunked extraction: the rows of one person are kept together when a big sheet is
    cut into pieces (chunking.py)

Pure functions, no database and no AI. When no table has a person column (a photo, a
handwritten sheet, free text), the answer is "unknown" (None): nothing is guessed."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

# A Markdown table separator line: | --- | :---: | ---: |
_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")

# Header words that name the person ...
_NAME_HEADER = re.compile(
    r"\bname\b|^(employee|worker|staff|associate|resource|contractor)$"
)
_CODE_HEADER = re.compile(
    r"^(emp(loyee)?|staff|worker|associate)?\s*(id|code|no|number|#)$"
    r"|^(emp(loyee)?|staff|worker)\s*(id|code|no|number|#)\b"
)
# ... but not another party or a pay code.
_NOT_PERSON = re.compile(
    r"\b(company|client|customer|project|job|pay|cost|site|task|supervisor|manager|"
    r"approver|approved|signed|location|department|dept|shift)\b"
)
# A people table also has a column for days, dates or hours. Without one it is a
# "label | value" block (e.g. "Employee Name | Rahul Kumar" above the hours table), and
# its rows are labels, not people.
_TIME_HEADER = re.compile(
    r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day)?\b|\bdate\b|\bday\b|\bhours?\b"
    r"|\bhrs\b|\btotal\b|\bweek\b|\btime\s*(in|out)\b|\bstart\b|\bend\b"
    r"|\d{4}-\d{2}-\d{2}|\b\d{1,2}[/.-]\d{1,2}\b|\b\d{1,2}\s*-?\s*[a-z]{3}\b"
)
# Values in a person column that are labels, never people.
_LABEL_VALUE = re.compile(
    r"^(employee|emp|staff|worker)?\s*(name|id|code|no|number)\s*:?$|^(week|period|pay\s*period)"
    r"(\s*(ending|starting|start|end|of|beginning))?\s*:?$|^(date|day|notes?|remarks?|"
    r"signature|supervisor|approved\s*by|signed|company|client)\b|:$"
)
_TOTAL_ROW = re.compile(r"^(grand\s*)?(sub\s*)?totals?\b|^sum\b")
_EMPTY_VALUES = frozenset({"", "-", "--", "n/a", "na", "none", "nil"})
_HAS_COUNT = re.compile(r"[1-9]")  # hours, times or dates: this row has data


@dataclass(slots=True)
class TableRow:
    line: str  # the row exactly as written (re-used when a sheet is cut into pieces)
    cells: list[str]


@dataclass(slots=True)
class Table:
    start: int  # line index of the header row
    end: int  # line index after the last row
    header_line: str
    separator_line: str
    header: list[str]
    rows: list[TableRow]
    name_col: int | None = None
    code_col: int | None = None

    @property
    def has_person_column(self) -> bool:
        return self.name_col is not None or self.code_col is not None


@dataclass(slots=True)
class PersonRows:
    """One person in one table, with all their rows (a weekly grid has one row; a
    one-row-per-day sheet has several, sometimes with the name only on the first)."""

    key: str
    code: str | None
    name: str | None
    rows: list[TableRow] = field(default_factory=list)
    has_data: bool = False  # at least one cell with hours / times / dates


@dataclass(slots=True)
class PeopleCount:
    people: list[PersonRows]

    @property
    def total(self) -> int:
        return len(self.people)

    def missing(
        self, extracted: Sequence[tuple[str | None, str | None]]
    ) -> list[PersonRows]:
        """People in the tables that the AI did not return. `extracted` holds
        (employee_code, employee_name) for each extracted timesheet. A person counts as
        found when either their code or their name matches."""
        codes = {norm_code(c) for c, _ in extracted if c and norm_code(c)}
        names = {norm_name(n) for _, n in extracted if n and norm_name(n)}
        return [
            p
            for p in self.people
            if not (
                (p.code is not None and norm_code(p.code) in codes)
                or (p.name is not None and norm_name(p.name) in names)
            )
        ]


def _plain(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("\\|", "|")).strip()


def norm_code(value: str) -> str:
    """'e-001' / 'E 001' -> 'E001'"""
    return re.sub(r"[^0-9A-Za-z]", "", _plain(value)).upper()


def norm_name(value: str) -> str:
    """'Kumar, Robert' / 'robert  kumar' -> 'kumar robert' (word order ignored)"""
    words = re.findall(r"[0-9a-z]+", _plain(value).lower())
    return " ".join(sorted(words))


def _header_key(value: str) -> str:
    return re.sub(r"[^0-9a-z#]+", " ", _plain(value).lower()).strip()


def _split_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [_plain(c) for c in _CELL_SPLIT.split(body)]


def _person_columns(header: list[str]) -> tuple[int | None, int | None]:
    name_col = code_col = None
    for index, raw in enumerate(header):
        key = _header_key(raw)
        if not key or _NOT_PERSON.search(key):
            continue
        if name_col is None and _NAME_HEADER.search(key):
            name_col = index
        elif code_col is None and _CODE_HEADER.search(key):
            code_col = index
    person = {c for c in (name_col, code_col) if c is not None}
    if person and not any(
        _TIME_HEADER.search(_header_key(raw))
        for i, raw in enumerate(header)
        if i not in person
    ):
        return None, None  # a "label | value" block, not a table of people
    return name_col, code_col


def parse_tables(markdown: str) -> list[Table]:
    """Every Markdown table in the text, with its person columns (if any)."""
    lines = markdown.splitlines()
    tables: list[Table] = []
    i = 0
    while i < len(lines) - 1:
        line, nxt = lines[i].strip(), lines[i + 1].strip()
        if line.startswith("|") and _SEPARATOR.match(nxt):
            j = i + 2
            rows: list[TableRow] = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(TableRow(lines[j], _split_cells(lines[j])))
                j += 1
            header = _split_cells(line)
            name_col, code_col = _person_columns(header)
            tables.append(
                Table(i, j, lines[i], lines[i + 1], header, rows, name_col, code_col)
            )
            i = j
        else:
            i += 1
    return tables


def _cell(row: TableRow, index: int | None) -> str | None:
    if index is None or index >= len(row.cells):
        return None
    value = row.cells[index]
    return None if value.lower() in _EMPTY_VALUES else value


def is_total_row(row: TableRow) -> bool:
    return any(_TOTAL_ROW.match(c.lower()) for c in row.cells[:3] if c)


def people_in_table(table: Table) -> tuple[list[TableRow], list[PersonRows]]:
    """(rows before the first person, people in order of first appearance). A row with
    an empty name / code continues the person above it; total rows are left out."""
    lead: list[TableRow] = []
    people: dict[str, PersonRows] = {}
    current: PersonRows | None = None
    if not table.has_person_column:
        return table.rows, []
    key_cols = {c for c in (table.name_col, table.code_col) if c is not None}
    for row in table.rows:
        if is_total_row(row) or not any(row.cells):
            continue
        code, name = _cell(row, table.code_col), _cell(row, table.name_col)
        if any(v is not None and _LABEL_VALUE.search(v.lower()) for v in (code, name)):
            continue  # "Week Ending | 2026-10-11" inside a table: a label row
        if code is None and name is None:
            if current is None:
                lead.append(row)  # a sub-header row before anyone is listed
                continue
            person = current  # continuation row: same person, next day
        else:
            key = f"c:{norm_code(code)}" if code else f"n:{norm_name(name or '')}"
            person = people.get(key) or PersonRows(key, code, name)
            people[key] = person
            person.code = person.code or code
            person.name = person.name or name
        person.rows.append(row)
        data = [c for i, c in enumerate(row.cells) if i not in key_cols]
        person.has_data = person.has_data or any(_HAS_COUNT.search(c) for c in data)
        current = person
    return lead, list(people.values())


def count_people(markdown: str) -> PeopleCount | None:
    """The people the document's tables list (only those with hours / dates / times on
    their rows), or None when no table has a name or employee-code column."""
    tables = [t for t in parse_tables(markdown) if t.has_person_column]
    if not tables:
        return None
    people: list[PersonRows] = []
    by_code: dict[str, PersonRows] = {}
    by_name: dict[str, PersonRows] = {}
    for table in tables:  # the same person on two sheets (weeks) counts once
        for person in people_in_table(table)[1]:
            if not person.has_data:
                continue  # a listed name with no hours at all: nothing to extract
            code = norm_code(person.code) if person.code else ""
            name = norm_name(person.name) if person.name else ""
            known = (by_code.get(code) if code else None) or (
                by_name.get(name) if name else None
            )
            if known is None:
                known = person
                people.append(person)
            known.code = known.code or person.code
            known.name = known.name or person.name
            if code:
                by_code[code] = known
            if name:
                by_name[name] = known
    return PeopleCount(people)


def label(person: PersonRows) -> str:
    if person.name and person.code:
        return f"{person.name} ({person.code})"
    return person.name or person.code or "?"


def missing_rows_flag(
    count: PeopleCount, missing: list[PersonRows]
) -> dict[str, object]:
    """The flag put on every timesheet of a document whose tables list people the AI
    did not return: none of them is approved automatically, and the reviewer knows who
    has no timesheet yet."""
    shown = ", ".join(label(p) for p in missing[:10])
    more = f" and {len(missing) - 10} more" if len(missing) > 10 else ""
    return {
        "code": "possible_missing_rows",
        "message": f"The sheet lists {count.total} people; "
        f"{count.total - len(missing)} were extracted. Missing: {shown}{more}. Check "
        "the original sheet: the missing people have no timesheet yet.",
        "people_in_tables": count.total,
        "missing": [label(p) for p in missing],
    }
