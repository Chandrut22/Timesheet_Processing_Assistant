"""bug.md #20 (no automatic approval on a guessed company) and #18 (reprocess asks
before clearing approvals: request schema and error)."""

import uuid
from decimal import Decimal

from src.core.exceptions import ConfirmationRequiredError, ConflictError
from src.core.services.company_matcher import CompanyRecord, decide_company
from src.core.services.timesheet_validation import can_auto_approve
from src.data.models import Timesheet, TimesheetEntry
from src.schemas.submission import ReprocessRequest

ABC = CompanyRecord(uuid.uuid4(), "ABC Staffing Solutions Pvt Ltd", ("ABC Staff.",))
NORTHWIND = CompanyRecord(uuid.uuid4(), "Northwind Workforce Partners", ("NWP",))
COMPANIES = [ABC, NORTHWIND]


def confident_timesheet(flag: dict[str, str] | None) -> Timesheet:
    return Timesheet(
        employee_id=uuid.uuid4(),
        confidence=Decimal("0.97"),
        flags=[flag] if flag else [],
        entries=[TimesheetEntry(hours=Decimal(8))],
    )


# --- #20 ---------------------------------------------------------------------------------


def test_exact_name_or_alias_still_allows_automatic_approval() -> None:
    for written in ("ABC Staffing Solutions", "ABC Staff."):
        decision = decide_company(written, None, COMPANIES)
        assert decision.company_id == ABC.id
        assert decision.flag is not None and decision.flag["code"] == "company_from_sheet"
        assert can_auto_approve(confident_timesheet(decision.flag))


def test_a_close_spelling_is_a_guess_and_needs_a_reviewer() -> None:
    decision = decide_company("ABC Stafing Solutions", None, COMPANIES)
    assert decision.company_id == ABC.id  # still used, so the right employees and rates apply
    assert decision.flag is not None and decision.flag["code"] == "company_guessed"
    assert "close spelling" in decision.flag["message"]
    assert not can_auto_approve(confident_timesheet(decision.flag))


def test_a_partial_name_is_a_guess_too() -> None:
    decision = decide_company("Northwind Workforce", None, COMPANIES)
    assert decision.company_id == NORTHWIND.id
    assert decision.flag is not None and decision.flag["code"] == "company_guessed"
    assert "start of the name" in decision.flag["message"]
    assert not can_auto_approve(confident_timesheet(decision.flag))


def test_the_sender_company_is_unchanged() -> None:
    decision = decide_company("ABC Stafing Solutions", ABC, COMPANIES)
    assert decision.company_id == ABC.id and decision.flag is None


def test_guessed_company_is_medium_severity() -> None:
    timesheet = confident_timesheet({"code": "company_guessed", "message": "m"})
    assert timesheet.severity == "medium"


# --- #18 ---------------------------------------------------------------------------------


def test_reprocess_does_not_clear_approvals_unless_asked() -> None:
    assert ReprocessRequest(reason="rates fixed").confirm_approved is False
    assert ReprocessRequest(reason="rates fixed", confirm_approved=True).confirm_approved


def test_confirmation_error_is_a_409_with_its_own_code() -> None:
    error = ConfirmationRequiredError("2 approved timesheet(s) would be replaced")
    assert isinstance(error, ConflictError)
    assert (error.status_code, error.code) == (409, "confirmation_required")


def test_classifier_switch_needs_a_real_key() -> None:
    import pytest

    from src.config.settings import Settings

    assert Settings(_env_file=None).classifier_enabled is False  # off by default
    for empty in ("", "   "):
        with pytest.raises(ValueError, match="needs JEV_API_KEY"):
            Settings(_env_file=None, classifier_enabled=True, jev_api_key=empty)
    assert Settings(_env_file=None, classifier_enabled=True, jev_api_key="k").classifier_enabled
