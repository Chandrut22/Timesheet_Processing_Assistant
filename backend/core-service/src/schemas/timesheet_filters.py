"""Filters and sorting for the review list (GET /timesheets).

Every filter is optional and they combine with AND. List filters (status, state,
severity) take several values by repeating the parameter:

    /timesheets?status=needs_review&severity=high&severity=medium&sort=confidence&order=asc
"""

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from src.constants.timesheet_status import SubmissionState, TimesheetStatus


class SeverityFilter(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"  # no flags at all


class TimesheetSort(StrEnum):
    RECEIVED = "received"  # when the email / upload arrived
    WEEK = "week"  # the week worked
    EMPLOYEE = "employee"  # matched employee's name, else the name as written
    HOURS = "hours"  # total hours
    GROSS = "gross"  # gross pay
    CONFIDENCE = "confidence"
    SEVERITY = "severity"  # high > medium > low > no flags


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class TimesheetFilters(BaseModel):
    status: list[TimesheetStatus] = Field(
        default_factory=list, description="Timesheet status; repeat for several"
    )
    state: list[SubmissionState] = Field(
        default_factory=list,
        description="State of the email / upload; repeat for several",
    )
    severity: list[SeverityFilter] = Field(
        default_factory=list, description="Worst flag severity; 'none' = no flags"
    )
    flag: str | None = Field(
        default=None, max_length=50, description="Has this flag, e.g. conflicting_hours"
    )
    submission_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    matched: bool | None = Field(
        default=None, description="true = employee matched, false = still unmatched"
    )
    sender: str | None = Field(
        default=None, max_length=255, description="Part of the sender's email address"
    )
    q: str | None = Field(
        default=None, max_length=100, description="Part of the employee name or code"
    )
    date_from: date | None = Field(
        default=None, description="Worked week overlaps from"
    )
    date_to: date | None = Field(default=None, description="Worked week overlaps until")
    received_from: date | None = Field(
        default=None, description="Arrived on or after (UTC)"
    )
    received_to: date | None = Field(
        default=None, description="Arrived on or before (UTC)"
    )
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    sort: TimesheetSort = TimesheetSort.RECEIVED
    order: SortOrder = SortOrder.DESC

    @model_validator(mode="after")
    def check_ranges(self) -> "TimesheetFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        if (
            self.received_from
            and self.received_to
            and self.received_from > self.received_to
        ):
            raise ValueError("received_from must not be after received_to")
        low, high = self.min_confidence, self.max_confidence
        if low is not None and high is not None and low > high:
            raise ValueError("min_confidence must not be above max_confidence")
        return self


class TimesheetListQuery(TimesheetFilters):
    """The filters plus paging: one model, so the API docs list every parameter."""

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
