"""Step 5: company names (case 1), three Johns (case 3), email vs attachment hours
(case 4), match confidence and reasons, assignment dates."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from src.core.services.company_matcher import (
    CompanyRecord,
    decide_company,
    match_company,
    normalize_company,
)
from src.core.services.employee_matcher import (
    EmployeeRecord,
    apply_match,
    match_employee,
    match_reason,
)
from src.core.services.timesheet_builder import (
    BuildContext,
    build_timesheet,
    conflicting_hours_flag,
)
from src.core.services.timesheet_validation import check_assignment
from src.data.models import Timesheet, TimesheetEntry
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet

ABC = CompanyRecord(uuid.uuid4(), "ABC Staffing Solutions Pvt Ltd", ("ABC Staff.",))
NORTHWIND = CompanyRecord(uuid.uuid4(), "Northwind Workforce Partners", ("NWP",))
BRIGHT = CompanyRecord(uuid.uuid4(), "BrightPath Talent Services")
COMPANIES = [ABC, NORTHWIND, BRIGHT]
MON = date(2026, 10, 5)


# --- companies (case 1) ---------------------------------------------------------------


def test_legal_words_and_punctuation_are_ignored() -> None:
    assert normalize_company("ABC Staffing Solutions Pvt. Ltd.") == "abc staffing solutions"


def test_company_found_by_name_alias_prefix_and_spelling() -> None:
    assert match_company("abc staffing solutions private limited", COMPANIES).company_id == ABC.id
    assert match_company("ABC Staff.", COMPANIES).method == "alias"
    assert match_company("Northwind Workforce", COMPANIES).method == "prefix"
    fuzzy = match_company("Northwnd Workforce Partners", COMPANIES)
    assert (fuzzy.company_id, fuzzy.method) == (NORTHWIND.id, "fuzzy")


def test_unknown_or_missing_company_name_is_not_matched() -> None:
    assert match_company("Contoso Ltd", COMPANIES).company_id is None
    assert match_company(None, COMPANIES).company_id is None
    assert match_company("Ltd", COMPANIES).company_id is None  # only legal words


def test_sheet_naming_another_company_wins_but_is_flagged() -> None:
    decision = decide_company("NWP", ABC, COMPANIES)
    assert decision.company_id == NORTHWIND.id
    assert decision.flag is not None and decision.flag["code"] == "company_mismatch"


def test_sender_company_used_when_sheet_agrees_or_is_silent() -> None:
    assert decide_company("ABC Staff.", ABC, COMPANIES).flag is None
    assert decide_company(None, ABC, COMPANIES) == decide_company(None, ABC, COMPANIES)
    assert decide_company(None, ABC, COMPANIES).company_id == ABC.id


def test_unknown_company_on_the_sheet_keeps_sender_but_flags() -> None:
    decision = decide_company("Contoso Ltd", ABC, COMPANIES)
    assert decision.company_id == ABC.id
    assert decision.flag is not None and "not a known company" in decision.flag["message"]


def test_upload_without_company_takes_it_from_the_sheet() -> None:
    decision = decide_company("ABC Staff.", None, COMPANIES)
    assert decision.company_id == ABC.id
    assert decision.flag is not None and decision.flag["code"] == "company_from_sheet"


# --- employees: confidence and reasons (cases 1 and 3) ----------------------------------


def emp(name: str, code: str, *aliases: str) -> EmployeeRecord:
    return EmployeeRecord(uuid.uuid4(), code, name, aliases)


def test_r_kumar_matches_by_initial_and_surname_with_a_reason() -> None:
    ramesh = emp("Ramesh Kumar", "SYN-EMP-101")
    result = match_employee("R. Kumar", None, [ramesh, emp("Priya Nair", "SYN-EMP-002")])
    assert (result.employee_id, result.method, result.confidence) == (
        ramesh.id,
        "initial_surname",
        0.85,
    )
    reason = match_reason(result, "R. Kumar", ramesh)
    assert reason.startswith("Matched Ramesh Kumar (SYN-EMP-101) by initial + surname")


def test_three_johns_are_not_matched_and_all_are_named() -> None:
    johns = [emp("John Abraham", "E7"), emp("John Mathew", "E9"), emp("John Paul", "E12")]
    result = match_employee("John", None, [*johns, emp("Priya Nair", "E2")])
    assert result.employee_id is None
    assert len(result.ambiguous) == 3
    reason = match_reason(result, "John", None)
    assert reason.startswith("3 employees fit 'John'")
    assert "John Mathew (E9)" in reason

    timesheet = Timesheet(flags=[], extracted_name="John", read_confidence=Decimal("0.95"))
    apply_match(timesheet, result)
    flag = next(f for f in timesheet.flags if f["code"] == "employee_unmatched")
    assert "3 employees fit 'John'" in flag["message"]
    assert timesheet.confidence == Decimal("0")


def test_a_single_john_matches_by_first_name_but_is_never_auto_approved() -> None:
    john = emp("John Mathew", "E9")
    result = match_employee("John", None, [john, emp("Priya Nair", "E2")])
    assert (result.employee_id, result.method, result.confidence) == (john.id, "first_name", 0.7)


def test_confidence_is_the_lower_of_reading_and_matching() -> None:
    priya = emp("Priya Nair", "E2", "P. Nair")
    timesheet = Timesheet(flags=[], extracted_name="P. Nair", read_confidence=Decimal("0.80"))
    apply_match(timesheet, match_employee("P. Nair", None, [priya]), matched=priya)
    assert timesheet.confidence == Decimal("0.8")  # reading (0.80) < alias (0.95)
    assert timesheet.match_reason is not None and "by alias 'P. Nair'" in timesheet.match_reason


# --- email vs attachment hours (case 4) ----------------------------------------------


def test_conflicting_hours_shows_both_values() -> None:
    flag = conflicting_hours_flag(Decimal("40"), Decimal("38"))
    assert flag is not None
    assert (flag["email_hours"], flag["attachment_hours"]) == (40.0, 38.0)
    assert "email says 40 h" in flag["message"] and "attachment says 38 h" in flag["message"]
    assert conflicting_hours_flag(Decimal("38"), Decimal("38")) is None
    assert conflicting_hours_flag(None, Decimal("38")) is None


def _extracted(email_total: float | None) -> ExtractedTimesheet:
    days = [
        ExtractedDay(work_date=MON + timedelta(days=i), hours=h)
        for i, h in enumerate([8, 8, 8, 8, 6])
    ]
    return ExtractedTimesheet(
        employee_name="Rahul Kumar",
        company_name="ABC Staff.",
        days=days,
        email_stated_total=email_total,
        confidence=0.95,
    )


def _ctx(is_email_body: bool = False) -> BuildContext:
    return BuildContext(uuid.uuid4(), uuid.uuid4(), None, MON, is_email_body=is_email_body)


def test_builder_flags_email_40_vs_attachment_38() -> None:
    timesheet = build_timesheet(_extracted(40), _ctx())
    assert timesheet.email_stated_total == Decimal("40.00")
    assert timesheet.extracted_company_name == "ABC Staff."
    assert timesheet.read_confidence == Decimal("0.95")
    assert any(f["code"] == "conflicting_hours" for f in timesheet.flags)


def test_no_conflict_when_the_email_body_is_the_timesheet() -> None:
    timesheet = build_timesheet(_extracted(40), _ctx(is_email_body=True))
    assert timesheet.email_stated_total is None
    assert not any(f["code"] == "conflicting_hours" for f in timesheet.flags)


# --- assignment dates -------------------------------------------------------------------


def _week(*hours: int) -> Timesheet:
    timesheet = Timesheet(flags=[])
    timesheet.entries = [
        TimesheetEntry(work_date=MON + timedelta(days=i), hours=Decimal(h))
        for i, h in enumerate(hours)
    ]
    return timesheet


def test_hours_outside_the_assignment_are_flagged() -> None:
    timesheet = _week(8, 8, 8, 8, 8)  # Mon 5 - Fri 9 Oct
    check_assignment(timesheet, date(2026, 10, 7), None)  # started on Wednesday
    flag = next(f for f in timesheet.flags if f["code"] == "outside_assignment")
    assert flag["dates"] == ["2026-10-05", "2026-10-06"]
    assert "2026-10-05 to 2026-10-06" in flag["message"]


def test_hours_inside_the_assignment_clear_the_flag() -> None:
    timesheet = _week(8, 8)
    check_assignment(timesheet, None, date(2026, 10, 5))
    assert any(f["code"] == "outside_assignment" for f in timesheet.flags)
    check_assignment(timesheet, date(2026, 10, 1), date(2026, 12, 31))  # dates corrected
    assert not any(f["code"] == "outside_assignment" for f in timesheet.flags)


def test_code_match_reason_quotes_the_code() -> None:
    elena = emp("Elena Petrova", "SYN-EMP-004")
    timesheet = Timesheet(
        flags=[],
        extracted_name="Elena Petrova",
        extracted_code="SYN-EMP-004",
        read_confidence=Decimal("0.95"),
    )
    result = match_employee("Elena Petrova", "SYN-EMP-004", [elena])
    apply_match(timesheet, result, matched=elena)
    assert timesheet.match_reason is not None
    assert "by employee code 'SYN-EMP-004'" in timesheet.match_reason
