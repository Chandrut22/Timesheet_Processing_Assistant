"""Employee matching: who is this timesheet for?

match_employee() is pure (no database): give it the extracted name/code and the
company's active employees. Only a single, unambiguous match is accepted; anything
else is left for a reviewer, with the closest candidates listed in a flag.

Order:
  1. Employee code             "E001", "e-001"
  2. Full name                 "Robert Kumar"
  3. Alias                     "Bob"  (aliases are set on the employee)
  4. Same words, other order   "Kumar, Robert"
  5. Initial + surname         "R. Kumar" / "Kumar R"  (only if exactly one fits)
  6. First name only           "John"  (only if exactly one John; never auto-approved)
  7. Close spelling            "Jon Smth" -> John Smith  (rank_shortlist; never
  auto-approved)

Step 7 combines two scorers. pg_trgm (Postgres, EmployeeRepository.similar_names, on the
indexed employees.name_keys column) finds the names that share enough letter triples,
fast and regardless of word order, with a low threshold so short typos are not lost.
difflib (here) then scores the spelling (as written and with the words sorted). A
close spelling is suggested only when difflib is sure (>= MATCH_FUZZY_ACCEPT), the next
employee is clearly behind (MATCH_FUZZY_MARGIN) and
pg_trgm ranks the same person first; otherwise the best ones are listed for a reviewer.

Each method has a confidence, and every result has a short reason a reviewer can read,
e.g. "Matched Rahul Kumar (SYN-EMP-001) by initial + surname 'R. Kumar'" or
"3 employees named 'John': John Abraham (E7), John Mathew (E9), John Paul (E12)".
"""

import re
import unicodedata
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from src.data.models import Employee, Timesheet

CANDIDATE_MIN_SCORE = 0.6
NAME_MISMATCH_BELOW = 0.6

# How sure each method is. The timesheet's confidence is the lower of this and the
# reading confidence, so a first-name-only match (0.70) always goes to a reviewer.
METHOD_CONFIDENCE: dict[str, float] = {
    "code": 1.0,
    "manual": 1.0,
    "name": 1.0,
    "alias": 0.95,
    "name_reordered": 0.9,
    "initial_surname": 0.85,
    "first_name": 0.7,
    "fuzzy": 0.75,
}
METHOD_LABEL: dict[str, str] = {
    "code": "employee code",
    "manual": "a reviewer",
    "name": "full name",
    "alias": "alias",
    "name_reordered": "name in another order",
    "initial_surname": "initial + surname",
    "first_name": "first name only",
    "fuzzy": "close spelling",
}

# Flags this module owns: removed and recomputed on every (re)match.
MATCH_FLAG_CODES = frozenset(
    {"employee_unmatched", "name_mismatch", "unknown_code", "no_company", "fuzzy_match"}
)
SPELLING_WEIGHT = (
    0.6  # combined score (for ordering the list): 0.6 spelling + 0.4 trigram
)


@dataclass(frozen=True, slots=True)
class EmployeeRecord:
    id: uuid.UUID
    code: str
    full_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Candidate:
    id: uuid.UUID
    code: str
    full_name: str
    score: float
    spelling: float | None = None  # difflib, for close spellings
    trigram: float | None = None  # pg_trgm, for close spellings
    company_id: uuid.UUID | None = (
        None  # set when suggested from another / unknown company
    )
    company_name: str | None = None


@dataclass(frozen=True, slots=True)
class Shortlisted:
    """One employee pg_trgm found, with its trigram similarity."""

    record: EmployeeRecord
    trigram: float
    company_id: uuid.UUID | None = None
    company_name: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    employee_id: uuid.UUID | None
    method: str | None
    candidates: tuple[Candidate, ...] = ()
    name_mismatch: bool = False  # matched by code, but the name looks like someone else
    code_not_found: bool = False  # a code was written but no employee has it
    ambiguous: tuple[
        Candidate, ...
    ] = ()  # several employees fit equally (e.g. three Johns)

    @property
    def confidence(self) -> float:
        return (
            METHOD_CONFIDENCE.get(self.method or "", 0.0) if self.employee_id else 0.0
        )


# --- text helpers ----------------------------------------------------------------


def normalize(text: str | None) -> str:
    """'José  O'Brien' -> 'jose o brien': lowercase, no accents, no punctuation."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", ascii_text.lower()).split())


def _code_key(code: str | None) -> str:
    """'E-001 ' -> 'e001'"""
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())


def _tokens(name: str | None) -> list[str]:
    return normalize(name).split()


def _all_names(employee: EmployeeRecord) -> list[str]:
    names = [normalize(employee.full_name), *(normalize(a) for a in employee.aliases)]
    return [n for n in names if n]


def _score(name: str, employee: EmployeeRecord) -> float:
    return max(
        (SequenceMatcher(None, name, n).ratio() for n in _all_names(employee)),
        default=0.0,
    )


def spelling_score(name: str, employee: EmployeeRecord) -> float:
    """difflib ratio against the full name and each alias, as written and with the words
    sorted ("Kumar Rahul" = "Rahul Kumar"); the best one."""
    ordered = " ".join(sorted(name.split()))
    best = 0.0
    for known in _all_names(employee):
        best = max(
            best,
            SequenceMatcher(None, name, known).ratio(),
            SequenceMatcher(None, ordered, " ".join(sorted(known.split()))).ratio(),
        )
    return best


def rank_shortlist(
    name: str | None,
    shortlist: Sequence[Shortlisted],
    *,
    accept: float,
    margin: float,
    allow_match: bool = True,
    limit: int = 3,
) -> MatchResult:
    """Pure: the close spellings pg_trgm found, scored by difflib. Returns a "fuzzy"
    match when it is safe (see the module docstring), else the best candidates (score =
    combined, with both scores kept). allow_match=False: suggestions only (no
    company)."""
    norm = normalize(name)
    if not norm or not shortlist:
        return MatchResult(None, None)
    scored: list[tuple[Shortlisted, float, float]] = []  # (item, spelling, combined)
    for item in shortlist:
        spelling = spelling_score(norm, item.record)
        combined = SPELLING_WEIGHT * spelling + (1 - SPELLING_WEIGHT) * item.trigram
        scored.append((item, spelling, combined))
    ranked = sorted(scored, key=lambda s: (-s[2], s[0].record.full_name))
    candidates = tuple(
        Candidate(
            item.record.id,
            item.record.code,
            item.record.full_name,
            round(combined, 2),
            spelling=round(spelling, 2),
            trigram=round(item.trigram, 2),
            company_id=item.company_id,
            company_name=item.company_name,
        )
        for item, spelling, combined in ranked[:limit]
    )
    by_spelling = sorted(scored, key=lambda s: (-s[1], s[0].record.full_name))
    top, top_spelling, _ = by_spelling[0]
    runner_up = by_spelling[1][1] if len(by_spelling) > 1 else 0.0
    best_trigram = max(item.trigram for item in shortlist)
    safe = (
        allow_match
        and len(norm.split()) >= 2  # one word ("John") is the first-name rule's job
        and top_spelling >= accept
        and top_spelling - runner_up >= margin
        and top.trigram >= best_trigram  # pg_trgm ranks the same person first
    )
    if safe:
        return MatchResult(top.record.id, "fuzzy", candidates=candidates)
    return MatchResult(None, None, candidates=candidates)


def _only_one(found: list[EmployeeRecord]) -> EmployeeRecord | None:
    return found[0] if len(found) == 1 else None


def _initial_surname(
    tokens: list[str], employees: Sequence[EmployeeRecord]
) -> list[EmployeeRecord]:
    """'r kumar' or 'kumar r' -> employees whose first name starts with r and surname is
    kumar."""
    if len(tokens) != 2:
        return []
    first, second = tokens
    if len(first) == 1 and len(second) > 1:
        initial, surname = first, second
    elif len(second) == 1 and len(first) > 1:
        initial, surname = second, first
    else:
        return []
    found = []
    for employee in employees:
        parts = _tokens(employee.full_name)
        if len(parts) >= 2 and parts[-1] == surname and parts[0].startswith(initial):
            found.append(employee)
    return found


def _candidates(
    name: str, employees: Sequence[EmployeeRecord], limit: int = 3
) -> tuple[Candidate, ...]:
    if not name:
        return ()
    scored = sorted(
        ((employee, _score(name, employee)) for employee in employees),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return tuple(
        Candidate(e.id, e.code, e.full_name, round(score, 2))
        for e, score in scored[:limit]
        if score >= CANDIDATE_MIN_SCORE
    )


# --- matching ----------------------------------------------------------------------


def match_employee(
    name: str | None, code: str | None, employees: Sequence[EmployeeRecord]
) -> MatchResult:
    norm = normalize(name)
    tokens = norm.split()

    key = _code_key(code)
    code_not_found = False
    if key:
        by_code = [e for e in employees if _code_key(e.code) == key]
        if len(by_code) == 1:
            employee = by_code[0]
            mismatch = (
                bool(norm)
                and _score(norm, employee) < NAME_MISMATCH_BELOW
                and not _initial_surname(tokens, [employee])
            )
            return MatchResult(employee.id, "code", name_mismatch=mismatch)
        code_not_found = not by_code

    if norm:
        rules: list[tuple[str, Callable[[EmployeeRecord], bool]]] = [
            ("name", lambda e: normalize(e.full_name) == norm),
            ("alias", lambda e: norm in {normalize(a) for a in e.aliases}),
            (
                "name_reordered",
                lambda e: sorted(_tokens(e.full_name)) == sorted(tokens),
            ),
        ]
        for method, fits in rules:
            hit = _only_one([e for e in employees if fits(e)])
            if hit:
                return MatchResult(hit.id, method, code_not_found=code_not_found)
        initial = _initial_surname(tokens, employees)
        hit = _only_one(initial)
        if hit:
            return MatchResult(hit.id, "initial_surname", code_not_found=code_not_found)
        if len(initial) > 1:
            return _ambiguous(initial, code_not_found)

        if len(tokens) == 1:  # "John": a first name only
            same_first = [e for e in employees if _tokens(e.full_name)[:1] == tokens]
            hit = _only_one(same_first)
            if hit:
                return MatchResult(hit.id, "first_name", code_not_found=code_not_found)
            if len(same_first) > 1:
                return _ambiguous(same_first, code_not_found)

    return MatchResult(
        None,
        None,
        candidates=_candidates(norm, employees),
        code_not_found=code_not_found,
    )


def _ambiguous(found: list[EmployeeRecord], code_not_found: bool) -> MatchResult:
    tied = tuple(Candidate(e.id, e.code, e.full_name, 1.0) for e in found)
    return MatchResult(
        None, None, candidates=tied, code_not_found=code_not_found, ambiguous=tied
    )


def describe(c: Candidate) -> str:
    """'John Smith (E7) at Lakeside (spelling 0.89, trigram 0.33)'"""
    text = f"{c.full_name} ({c.code})"
    if c.company_name:
        text += f" at {c.company_name}"
    if c.spelling is not None and c.trigram is not None:
        text += f" (spelling {c.spelling:.2f}, trigram {c.trigram:.2f})"
    return text


def candidate_json(c: Candidate) -> dict[str, Any]:
    """A candidate as stored in a flag (the review page lists them as suggestions)."""
    item: dict[str, Any] = {
        "id": str(c.id),
        "code": c.code,
        "name": c.full_name,
        "score": c.score,
    }
    if c.spelling is not None:
        item["spelling"] = c.spelling
    if c.trigram is not None:
        item["trigram"] = c.trigram
    if c.company_id is not None:
        item["company_id"] = str(c.company_id)
    if c.company_name:
        item["company"] = c.company_name
    return item


def match_reason(result: MatchResult, who: str, matched: EmployeeRecord | None) -> str:
    """One plain sentence: why this employee, or why nobody."""
    if result.method == "fuzzy" and matched is not None:
        scores = next((c for c in result.candidates if c.id == matched.id), None)
        how = (
            f" (spelling {scores.spelling:.2f}, trigram {scores.trigram:.2f})"
            if scores and scores.spelling is not None and scores.trigram is not None
            else ""
        )
        return (
            f"Suggested {matched.full_name} ({matched.code}): close spelling of "
            f"'{who}'{how}. A reviewer must confirm it."
        )
    if result.employee_id is not None and matched is not None:
        how = METHOD_LABEL.get(result.method or "", result.method or "?")
        return (
            f"Matched {matched.full_name} ({matched.code}) by {how} '{who}' (match "
            f"confidence {result.confidence:.2f})."
        )
    if result.ambiguous:
        names = ", ".join(f"{c.full_name} ({c.code})" for c in result.ambiguous)
        return (
            f"{len(result.ambiguous)} employees fit '{who}': {names}. A reviewer must "
            "choose."
        )
    if result.candidates:
        names = ", ".join(describe(c) for c in result.candidates)
        return f"No exact match for '{who}'. Closest: {names}."
    return f"No employee found for '{who}'."


# --- glue to the models (still no database access) ---------------------------------


def to_record(employee: Employee) -> EmployeeRecord:
    return EmployeeRecord(
        id=employee.id,
        code=employee.employee_code,
        full_name=employee.full_name,
        aliases=tuple(employee.aliases or ()),
    )


def apply_match(
    timesheet: Timesheet,
    result: MatchResult,
    *,
    company_known: bool = True,
    matched: EmployeeRecord | None = None,
) -> None:
    """Store the match (employee, method, confidence, reason) and rebuild the matching
    flags. `matched` is the matched employee's record, used for the reason text."""
    timesheet.employee_id = result.employee_id
    timesheet.match_method = result.method
    # Confidence = the lower of "how well it was read" and "how sure the match is".
    read = (
        float(timesheet.read_confidence)
        if timesheet.read_confidence is not None
        else 1.0
    )
    timesheet.confidence = Decimal(str(round(min(read, result.confidence), 2)))

    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in MATCH_FLAG_CODES
    ]
    who = timesheet.extracted_name or timesheet.extracted_code or "this timesheet"
    # Matched by code: quote the code that was written, not the name.
    shown = (
        timesheet.extracted_code
        if result.method == "code" and timesheet.extracted_code
        else who
    )
    suggestions = ", ".join(describe(c) for c in result.candidates)
    timesheet.match_reason = (
        match_reason(result, shown, matched)
        if company_known
        else "No company known, so no employee list to match against."
        + (f" Close names in other companies: {suggestions}." if suggestions else "")
    )

    if not company_known:
        flags.append(
            {
                "code": "no_company",
                "message": "No company set: choose the company and employee in review."
                + (f" Possible: {suggestions}." if suggestions else ""),
                "candidates": [candidate_json(c) for c in result.candidates],
            }
        )
    elif result.method == "fuzzy" and matched is not None:
        others = [describe(c) for c in result.candidates if c.id != matched.id]
        flags.append(
            {
                "code": "fuzzy_match",
                "message": f"'{who}' is not written exactly like {matched.full_name}'s "
                "name (close spelling). Check it is the same person."
                + (f" Others: {', '.join(others)}." if others else ""),
                "candidates": [candidate_json(c) for c in result.candidates],
            }
        )
    elif result.employee_id is None:
        if result.ambiguous:
            options = ", ".join(f"{c.full_name} ({c.code})" for c in result.ambiguous)
            message = (
                f"{len(result.ambiguous)} employees fit '{who}': {options}. Choose one."
            )
        elif result.candidates:
            options = ", ".join(f"{c.full_name} ({c.code})" for c in result.candidates)
            message = f"No unique employee for '{who}'. Possible: {options}."
        else:
            message = f"No employee found for '{who}'. Add the employee or an alias."
        flags.append(
            {
                "code": "employee_unmatched",
                "message": message,
                "candidates": [candidate_json(c) for c in result.candidates],
            }
        )
    if result.name_mismatch:
        flags.append(
            {
                "code": "name_mismatch",
                "message": f"Matched by code, but the name '{who}' looks different. "
                "Check it.",
            }
        )
    if result.code_not_found and timesheet.extracted_code:
        flags.append(
            {
                "code": "unknown_code",
                "message": f"Employee code '{timesheet.extracted_code}' is not in this "
                "company.",
            }
        )
    timesheet.flags = flags  # a new list, so SQLAlchemy saves the JSONB change
