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
"""

import re
import unicodedata
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from src.data.models import Employee, Timesheet

CANDIDATE_MIN_SCORE = 0.6
NAME_MISMATCH_BELOW = 0.6

# Flags this module owns: removed and recomputed on every (re)match.
MATCH_FLAG_CODES = frozenset({"employee_unmatched", "name_mismatch", "unknown_code", "no_company"})


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


@dataclass(frozen=True, slots=True)
class MatchResult:
    employee_id: uuid.UUID | None
    method: str | None
    candidates: tuple[Candidate, ...] = ()
    name_mismatch: bool = False  # matched by code, but the name looks like someone else
    code_not_found: bool = False  # a code was written but no employee has it


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
    return max((SequenceMatcher(None, name, n).ratio() for n in _all_names(employee)), default=0.0)


def _only_one(found: list[EmployeeRecord]) -> EmployeeRecord | None:
    return found[0] if len(found) == 1 else None


def _initial_surname(
    tokens: list[str], employees: Sequence[EmployeeRecord]
) -> list[EmployeeRecord]:
    """'r kumar' or 'kumar r' -> employees whose first name starts with r and surname is kumar."""
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
            ("name_reordered", lambda e: sorted(_tokens(e.full_name)) == sorted(tokens)),
        ]
        for method, fits in rules:
            hit = _only_one([e for e in employees if fits(e)])
            if hit:
                return MatchResult(hit.id, method, code_not_found=code_not_found)
        hit = _only_one(_initial_surname(tokens, employees))
        if hit:
            return MatchResult(hit.id, "initial_surname", code_not_found=code_not_found)

    return MatchResult(
        None, None, candidates=_candidates(norm, employees), code_not_found=code_not_found
    )


# --- glue to the models (still no database access) ---------------------------------


def to_record(employee: Employee) -> EmployeeRecord:
    return EmployeeRecord(
        id=employee.id,
        code=employee.employee_code,
        full_name=employee.full_name,
        aliases=tuple(employee.aliases or ()),
    )


def apply_match(timesheet: Timesheet, result: MatchResult, *, company_known: bool = True) -> None:
    """Store the match on the timesheet and rebuild the matching flags."""
    timesheet.employee_id = result.employee_id
    timesheet.match_method = result.method

    flags: list[dict[str, Any]] = [
        f for f in (timesheet.flags or []) if f.get("code") not in MATCH_FLAG_CODES
    ]
    who = timesheet.extracted_name or timesheet.extracted_code or "this timesheet"

    if not company_known:
        flags.append(
            {
                "code": "no_company",
                "message": "No company set: choose the company and employee in review.",
            }
        )
    elif result.employee_id is None:
        if result.candidates:
            options = ", ".join(f"{c.full_name} ({c.code})" for c in result.candidates)
            message = f"No unique employee for '{who}'. Possible: {options}."
        else:
            message = f"No employee found for '{who}'. Add the employee or an alias."
        flags.append(
            {
                "code": "employee_unmatched",
                "message": message,
                "candidates": [
                    {"id": str(c.id), "code": c.code, "name": c.full_name, "score": c.score}
                    for c in result.candidates
                ],
            }
        )
    if result.name_mismatch:
        flags.append(
            {
                "code": "name_mismatch",
                "message": f"Matched by code, but the name '{who}' looks different. Check it.",
            }
        )
    if result.code_not_found and timesheet.extracted_code:
        flags.append(
            {
                "code": "unknown_code",
                "message": f"Employee code '{timesheet.extracted_code}' is not in this company.",
            }
        )
    timesheet.flags = flags  # a new list, so SQLAlchemy saves the JSONB change
