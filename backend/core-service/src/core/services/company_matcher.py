"""Company matching: which client company does the name written on a sheet mean?

match_company() is pure (no database). Company names are compared after removing
case, punctuation and legal words ("Pvt", "Ltd", "Inc", ...), so these all match
"ABC Staffing Solutions Pvt Ltd":

    "ABC Staffing Solutions"   (same name without the legal words)
    "ABC Staff."               (an alias set on the company)
    "abc staffing solutions private limited"

Order: exact name -> alias -> one company whose name starts with the written name
(at least 2 words, e.g. "ABC Staffing") -> one close spelling (similarity >= 0.88).
Only a single, unambiguous company is accepted."""

import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

LEGAL_WORDS = frozenset(
    {
        "pvt",
        "private",
        "ltd",
        "limited",
        "llp",
        "llc",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "plc",
        "gmbh",
        "the",
    }
)
FUZZY_MIN = 0.88


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    id: uuid.UUID
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompanyMatch:
    company_id: uuid.UUID | None
    method: str | None  # name | alias | prefix | fuzzy
    company_name: str | None = None
    score: float = 0.0


def normalize_company(text: str | None) -> str:
    """'ABC Staffing Solutions Pvt. Ltd.' -> 'abc staffing solutions'"""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9& ]+", " ", ascii_text.lower()).split()
    return " ".join(w for w in words if w not in LEGAL_WORDS)


def _one(found: list[CompanyRecord]) -> CompanyRecord | None:
    unique = {c.id: c for c in found}
    return next(iter(unique.values())) if len(unique) == 1 else None


def match_company(written: str | None, companies: Sequence[CompanyRecord]) -> CompanyMatch:
    norm = normalize_company(written)
    if not norm:
        return CompanyMatch(None, None)

    exact = _one([c for c in companies if normalize_company(c.name) == norm])
    if exact:
        return CompanyMatch(exact.id, "name", exact.name, 1.0)

    alias = _one([c for c in companies if norm in {normalize_company(a) for a in c.aliases}])
    if alias:
        return CompanyMatch(alias.id, "alias", alias.name, 1.0)

    if len(norm.split()) >= 2:
        prefix = _one([c for c in companies if normalize_company(c.name).startswith(norm + " ")])
        if prefix:
            return CompanyMatch(prefix.id, "prefix", prefix.name, 0.9)

    scored = sorted(
        (
            (
                max(
                    SequenceMatcher(None, norm, n).ratio()
                    for n in [normalize_company(c.name), *(normalize_company(a) for a in c.aliases)]
                    if n
                )
                if normalize_company(c.name)
                else 0.0,
                c,
            )
            for c in companies
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if scored and scored[0][0] >= FUZZY_MIN and (len(scored) == 1 or scored[1][0] < FUZZY_MIN):
        score, best = scored[0]
        return CompanyMatch(best.id, "fuzzy", best.name, round(score, 2))
    return CompanyMatch(None, None)


@dataclass(frozen=True, slots=True)
class CompanyDecision:
    """Which company a timesheet is for, and any flag to raise about it."""

    company_id: uuid.UUID | None
    flag: dict[str, str] | None = None


def decide_company(
    written: str | None,
    sender_company: CompanyRecord | None,
    companies: Sequence[CompanyRecord],
) -> CompanyDecision:
    """Pure. The sender's company (from the whitelist, or chosen on upload) is used,
    unless the sheet clearly names ANOTHER known company: then that company is used
    (so the right employees and rates apply) and a reviewer must confirm."""
    found = match_company(written, companies)

    if sender_company is None:
        if found.company_id is None:
            return CompanyDecision(None)
        return CompanyDecision(
            found.company_id,
            {
                "code": "company_from_sheet",
                "message": f"Company taken from the sheet: '{written}' = {found.company_name} "
                f"(by {found.method}).",
            },
        )

    if found.company_id is None or found.company_id == sender_company.id:
        if written and found.company_id is None:
            return CompanyDecision(
                sender_company.id,
                {
                    "code": "company_mismatch",
                    "message": f"The sheet names '{written}', which is not a known company. "
                    f"Used {sender_company.name} (from the sender). Check it.",
                },
            )
        return CompanyDecision(sender_company.id)

    return CompanyDecision(
        found.company_id,
        {
            "code": "company_mismatch",
            "message": f"The sheet is for {found.company_name} ('{written}'), but the sender "
            f"belongs to {sender_company.name}. Used {found.company_name}. Confirm it.",
        },
    )
