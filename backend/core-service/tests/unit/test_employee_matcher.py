import uuid

from src.core.services.employee_matcher import EmployeeRecord, match_employee, normalize


def emp(code: str, name: str, *aliases: str) -> EmployeeRecord:
    return EmployeeRecord(id=uuid.uuid4(), code=code, full_name=name, aliases=aliases)


ROBERT = emp("E001", "Robert Kumar", "Bob")
PRIYA = emp("E002", "Priya Sharma")
RAVI = emp("E003", "Ravi Kumar")
STAFF = [ROBERT, PRIYA, RAVI]


def test_normalize() -> None:
    assert normalize("  José  O'Brien ") == "jose o brien"


def test_match_by_code_ignores_case_and_dashes() -> None:
    result = match_employee(None, "e-001", STAFF)
    assert (result.employee_id, result.method) == (ROBERT.id, "code")


def test_code_wins_but_flags_a_different_name() -> None:
    result = match_employee("Priya Sharma", "E001", STAFF)
    assert result.employee_id == ROBERT.id
    assert result.name_mismatch


def test_match_by_full_name() -> None:
    assert match_employee("robert KUMAR", None, STAFF).method == "name"


def test_match_by_alias() -> None:
    result = match_employee("Bob", None, STAFF)
    assert (result.employee_id, result.method) == (ROBERT.id, "alias")


def test_match_reordered_name() -> None:
    result = match_employee("Kumar, Robert", None, STAFF)
    assert (result.employee_id, result.method) == (ROBERT.id, "name_reordered")


def test_initial_and_surname_when_unique() -> None:
    result = match_employee("P. Sharma", None, STAFF)
    assert (result.employee_id, result.method) == (PRIYA.id, "initial_surname")


def test_initial_and_surname_ambiguous_is_not_matched() -> None:
    # R. Kumar fits both Robert Kumar and Ravi Kumar -> reviewer decides
    result = match_employee("R. Kumar", None, STAFF)
    assert result.employee_id is None
    assert {c.id for c in result.candidates} >= {ROBERT.id, RAVI.id}


def test_typo_gives_candidates_not_a_match() -> None:
    result = match_employee("Robertt Kumarr", None, STAFF)
    assert result.employee_id is None
    assert result.candidates[0].id == ROBERT.id


def test_unknown_code_falls_back_to_name() -> None:
    result = match_employee("Priya Sharma", "E999", STAFF)
    assert (result.employee_id, result.method) == (PRIYA.id, "name")
    assert result.code_not_found


def test_two_people_same_name_is_not_matched() -> None:
    twin = emp("E004", "Priya Sharma")
    result = match_employee("Priya Sharma", None, [*STAFF, twin])
    assert result.employee_id is None
    assert len(result.candidates) >= 2
