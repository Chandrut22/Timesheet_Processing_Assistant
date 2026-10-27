"""Close spellings: pg_trgm shortlists (its scores are given here), difflib decides.

A close spelling is only suggested when difflib is sure, the next employee is clearly
behind and pg_trgm ranks the same person first; it is never auto-approved."""

import uuid
from decimal import Decimal

from src.core.services.employee_matcher import (
    EmployeeRecord,
    MatchResult,
    Shortlisted,
    apply_match,
    match_reason,
    rank_shortlist,
    spelling_score,
)
from src.data.models import Timesheet

ACCEPT, MARGIN = 0.85, 0.10


def emp(name: str, code: str, *aliases: str) -> EmployeeRecord:
    return EmployeeRecord(uuid.uuid4(), code, name, tuple(aliases))


JOHN = emp("John Smith", "E7")
JOAN = emp("Joan Smith", "E8")
PRIYA = emp("Priya Nair", "E9", "Priya N")
RAHUL = emp("Rahul Kumar", "E1")
RAHULI = emp("Rahul Kumari", "E2")


def rank(name: str, *items: Shortlisted, allow_match: bool = True) -> MatchResult:
    return rank_shortlist(name, items, accept=ACCEPT, margin=MARGIN, allow_match=allow_match)


def test_a_typo_is_suggested_even_though_trigrams_score_it_low() -> None:
    result = rank("Jon Smth", Shortlisted(JOHN, 0.33), Shortlisted(PRIYA, 0.05))
    assert result.employee_id == JOHN.id
    assert result.method == "fuzzy"
    assert result.confidence == 0.75  # below auto-approve (0.85): a reviewer confirms
    top = result.candidates[0]
    assert (top.full_name, top.spelling, top.trigram) == ("John Smith", 0.89, 0.33)


def test_word_order_does_not_matter() -> None:
    assert spelling_score("smith jon", JOHN) == spelling_score("jon smith", JOHN)
    assert rank("Smth, Jon", Shortlisted(JOHN, 0.4)).employee_id == JOHN.id


def test_two_close_employees_are_left_to_a_reviewer() -> None:
    result = rank("Jhon Smith", Shortlisted(JOHN, 0.5), Shortlisted(JOAN, 0.45))
    assert result.employee_id is None
    assert {c.full_name for c in result.candidates} == {"John Smith", "Joan Smith"}


def test_a_name_one_letter_longer_is_not_picked_over_the_other() -> None:
    result = rank("Rahul Kumr", Shortlisted(RAHUL, 0.64), Shortlisted(RAHULI, 0.55))
    assert result.employee_id is None  # 0.95 vs 0.91: too close to choose


def test_the_two_scorers_must_agree() -> None:
    # difflib prefers John, pg_trgm prefers Joan: no suggestion
    result = rank("Jon Smiht", Shortlisted(JOHN, 0.30), Shortlisted(PRIYA, 0.40))
    assert result.employee_id is None
    assert result.candidates  # still listed for the reviewer


def test_not_close_enough_or_one_word() -> None:
    assert rank("Jane Doe", Shortlisted(JOHN, 0.25)).employee_id is None
    assert rank("Jon", Shortlisted(JOHN, 0.4)).employee_id is None  # first-name rule's job
    assert rank("", Shortlisted(JOHN, 0.4)).candidates == ()
    assert rank("Jon Smth").candidates == ()


def test_aliases_count() -> None:
    assert rank("Priya Nr", Shortlisted(PRIYA, 0.5)).employee_id == PRIYA.id


def test_suggestions_only_for_an_unknown_company() -> None:
    company = uuid.uuid4()
    result = rank(
        "Jon Smth",
        Shortlisted(JOHN, 0.33, company_id=company, company_name="Lakeside"),
        allow_match=False,
    )
    assert result.employee_id is None
    assert result.candidates[0].company_name == "Lakeside"


def test_a_suggested_match_is_flagged_and_explained() -> None:
    result = rank("Jon Smth", Shortlisted(JOHN, 0.33), Shortlisted(PRIYA, 0.05))
    t = Timesheet(extracted_name="Jon Smth", flags=[], read_confidence=Decimal("0.95"))
    apply_match(t, result, matched=JOHN)
    assert t.employee_id == JOHN.id and t.match_method == "fuzzy"
    assert t.confidence == Decimal("0.75")
    (flag,) = [f for f in t.flags if f["code"] == "fuzzy_match"]
    assert "Check it is the same person" in flag["message"]
    assert flag["candidates"][0]["spelling"] == 0.89
    assert "spelling 0.89, trigram 0.33" in (t.match_reason or "")
    assert match_reason(result, "Jon Smth", JOHN).startswith("Suggested John Smith (E7)")


def test_no_company_lists_close_names_from_other_companies() -> None:
    company = uuid.uuid4()
    result = rank(
        "Jon Smth",
        Shortlisted(JOHN, 0.33, company_id=company, company_name="Lakeside"),
        allow_match=False,
    )
    t = Timesheet(extracted_name="Jon Smth", flags=[])
    apply_match(t, result, company_known=False)
    (flag,) = [f for f in t.flags if f["code"] == "no_company"]
    assert "John Smith (E7) at Lakeside" in flag["message"]
    assert flag["candidates"][0]["company_id"] == str(company)
    assert t.employee_id is None
