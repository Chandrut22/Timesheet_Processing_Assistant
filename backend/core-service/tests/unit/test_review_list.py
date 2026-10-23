"""Step 6: review-list filters and sorting (the SQL they build) and bulk requests."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from src.constants.timesheet_status import TimesheetStatus
from src.core.services.review_service import _summary
from src.data.models import Timesheet
from src.data.repositories.timesheet_repository import _conditions, _order_by
from src.schemas.review import BulkApproveRequest, BulkItemResult, BulkRejectRequest
from src.schemas.timesheet_filters import (
    SeverityFilter,
    SortOrder,
    TimesheetFilters,
    TimesheetListQuery,
    TimesheetSort,
)

# The PostgreSQL dialect, to compile queries without connecting to a database.
PG = create_async_engine("postgresql+asyncpg://test@localhost/test").dialect


def sql(filters: TimesheetFilters) -> str:
    query = select(Timesheet.id).where(*_conditions(filters)).order_by(*_order_by(filters))
    return str(query.compile(dialect=PG))


def params(filters: TimesheetFilters) -> set[object]:
    query = select(Timesheet.id).where(*_conditions(filters))
    return set(query.compile(dialect=PG).params.values())


# --- filters -----------------------------------------------------------------------


def test_every_status_is_listed_by_default() -> None:
    # No hidden "superseded" versions any more: a reprocess updates in place.
    assert "core.timesheets.status" not in sql(TimesheetFilters())
    rejected = TimesheetFilters(status=[TimesheetStatus.REJECTED])
    assert "core.timesheets.status IN" in sql(rejected)


def test_severity_none_means_no_flags() -> None:
    text = sql(TimesheetFilters(severity=[SeverityFilter.HIGH, SeverityFilter.NONE]))
    assert "core.timesheets.severity IN" in text
    assert "core.timesheets.severity IS NULL" in text


def test_text_filters_take_percent_and_underscore_literally() -> None:
    filters = TimesheetFilters(q="100%_x")
    assert "%100\\%\\_x%" in params(filters)


def test_a_week_overlapping_the_date_range_is_included() -> None:
    filters = TimesheetFilters(date_from=date(2026, 10, 7), date_to=date(2026, 10, 7))
    values = params(filters)
    assert date(2026, 10, 1) in values  # a week starting up to 6 days earlier still overlaps
    assert date(2026, 10, 7) in values


def test_flag_filter_uses_jsonb_containment() -> None:
    assert "core.timesheets.flags @>" in sql(TimesheetFilters(flag="conflicting_hours"))


def test_ranges_must_be_in_order() -> None:
    with pytest.raises(ValidationError, match="date_from must not be after date_to"):
        TimesheetFilters(date_from=date(2026, 10, 10), date_to=date(2026, 10, 1))
    with pytest.raises(ValidationError, match="min_confidence"):
        TimesheetFilters(min_confidence=0.9, max_confidence=0.5)
    with pytest.raises(ValidationError):
        TimesheetListQuery(size=500)


# --- sorting -----------------------------------------------------------------------


def test_severity_sort_ranks_high_first_and_empty_values_last() -> None:
    text = sql(TimesheetFilters(sort=TimesheetSort.SEVERITY, order=SortOrder.DESC))
    assert "CASE WHEN" in text and "DESC NULLS LAST" in text
    gross = TimesheetFilters(sort=TimesheetSort.GROSS, order=SortOrder.ASC)
    assert "ASC NULLS LAST" in sql(gross)


def test_every_sort_ends_with_a_stable_tie_breaker() -> None:
    for sort in TimesheetSort:
        assert sql(TimesheetFilters(sort=sort)).rstrip().endswith("core.timesheets.id")


# --- bulk --------------------------------------------------------------------------


def test_bulk_drops_repeated_ids_and_keeps_the_order() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert BulkApproveRequest(timesheet_ids=[a, b, a]).timesheet_ids == [a, b]


def test_bulk_needs_1_to_100_ids_and_a_reason_to_reject() -> None:
    with pytest.raises(ValidationError):
        BulkApproveRequest(timesheet_ids=[])
    with pytest.raises(ValidationError):
        BulkApproveRequest(timesheet_ids=[uuid.uuid4() for _ in range(101)])
    with pytest.raises(ValidationError):
        BulkRejectRequest(timesheet_ids=[uuid.uuid4()], reason="")


def test_bulk_summary_counts_successes_and_failures() -> None:
    results = [
        BulkItemResult(timesheet_id=uuid.uuid4(), ok=True, status="approved"),
        BulkItemResult(timesheet_id=uuid.uuid4(), ok=False, status=None, error="not found"),
    ]
    summary = _summary(results)
    assert (summary.requested, summary.succeeded, summary.failed) == (2, 1, 1)
