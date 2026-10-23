import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.constants.flags import Severity, highest_severity, with_severity
from src.constants.timesheet_status import TimesheetStatus
from src.data.models.base import SCHEMA, Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_check
from src.data.models.timesheet_entry import EntryList, TimesheetEntry, check_entries

ZERO = text("0")


class Timesheet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One person's week, extracted from a document."""

    __tablename__ = "timesheets"
    __table_args__ = (
        enum_check("status", TimesheetStatus),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        Index("ix_timesheets_employee_week", "employee_id", "week_start"),  # duplicate check
        enum_check("severity", Severity),
        CheckConstraint(
            "(regular_amount IS NULL OR regular_amount >= 0) "
            "AND (overtime_amount IS NULL OR overtime_amount >= 0) "
            "AND (double_time_amount IS NULL OR double_time_amount >= 0) "
            "AND (holiday_amount IS NULL OR holiday_amount >= 0)",
            name="amounts_non_negative",
        ),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("jsonb_typeof(entries) = 'array'", name="entries_is_array"),
        CheckConstraint(
            "email_stated_total IS NULL OR email_stated_total >= 0",
            name="email_stated_total_non_negative",
        ),
        CheckConstraint(
            "read_confidence IS NULL OR (read_confidence >= 0 AND read_confidence <= 1)",
            name="read_confidence_range",
        ),
        CheckConstraint(
            "regular_hours >= 0 AND overtime_hours >= 0 AND double_time_hours >= 0 "
            "AND holiday_hours >= 0 AND (stated_total IS NULL OR stated_total >= 0)",
            name="hours_non_negative",
        ),
        # A decision (approve / reject / export) always has a time.
        CheckConstraint(
            "status NOT IN ('approved', 'rejected', 'exported') OR reviewed_at IS NOT NULL",
            name="decided_has_time",
        ),
        # An exported timesheet always points to its export batch.
        CheckConstraint(
            "status <> 'exported' OR (export_batch_id IS NOT NULL AND exported_at IS NOT NULL)",
            name="exported_has_batch",
        ),
        Index("ix_timesheets_employee_week", "employee_id", "week_start"),  # duplicate check
        Index("ix_timesheets_week_start", "week_start"),  # date filter / sort in review list
        # flag=... filter in the review list (jsonb containment, @>)
        Index(
            "ix_timesheets_flags",
            "flags",
            postgresql_using="gin",
            postgresql_ops={"flags": "jsonb_path_ops"},
        ),
    )

    # Same service -> real foreign keys
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.companies.id", ondelete="RESTRICT"), index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(  # None until matched
        Uuid, ForeignKey(f"{SCHEMA}.employees.id", ondelete="RESTRICT"), index=True
    )
    # Version of the data (days, employee, week, pay): 1 when extracted, + 1 on every
    # change by a reviewer, a reprocess or a rollback. Each earlier version is kept in
    # timesheet_versions (see version_history.py), so any of them can be restored.
    version: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text("1"))
    reprocess_run_id: Mapped[uuid.UUID | None] = mapped_column(  # last reprocess that changed it
        Uuid, ForeignKey(f"{SCHEMA}.reprocess_runs.id", ondelete="SET NULL"), index=True
    )

    # What the document said (kept even after matching, for the reviewer)
    extracted_name: Mapped[str | None] = mapped_column(String(200))
    extracted_code: Mapped[str | None] = mapped_column(String(50))
    extracted_company_name: Mapped[str | None] = mapped_column(String(200))  # as written
    week_start: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(
        String(20), default=TimesheetStatus.NEEDS_REVIEW, server_default="needs_review", index=True
    )
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    double_time_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=0, server_default=ZERO
    )
    holiday_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, server_default=ZERO)
    # Calculated by PostgreSQL, so it can never differ from its parts (read-only here).
    total_hours: Mapped[Decimal] = mapped_column(
        Numeric(7, 2),
        Computed("regular_hours + overtime_hours + double_time_hours + holiday_hours"),
    )
    stated_total: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2)
    )  # total written on the sheet
    # Total hours the EMAIL BODY gives for this person (compared with the attachment).
    email_stated_total: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    read_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))  # how well it was read
    # Overall: the lower of read_confidence and the match method's confidence.
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))  # 0.00 - 1.00
    # Pay: the company's rates are COPIED here when the hours are calculated, so a later
    # rate change never alters this timesheet. None = not priced (no company / no rate).
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    overtime_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    double_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    holiday_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    regular_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    overtime_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    double_time_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    holiday_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Gross pay (no taxes or deductions). Calculated by PostgreSQL; NULL if any part is NULL.
    gross_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("regular_amount + overtime_amount + double_time_amount + holiday_amount"),
    )
    match_method: Mapped[str | None] = mapped_column(String(30))  # code / email / name / alias ...
    match_reason: Mapped[str | None] = mapped_column(Text)  # plain sentence for the reviewer
    # [{"code": "total_mismatch", "message": "Sheet says 42, entries add up to 40"}]
    flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # Other service (auth) -> UUID reference + name snapshot, NO foreign key
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewed_by_name: Mapped[str | None] = mapped_column(String(150))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The days, in date order (see timesheet_entry.py). [] for a weekly-total sheet.
    entries: Mapped[list[TimesheetEntry]] = mapped_column(
        MutableList.as_mutable(EntryList()), default=list, server_default=text("'[]'::jsonb")
    )

    # Which payroll sheet it went into. Set once; a timesheet is never exported twice.
    export_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.export_batches.id", ondelete="RESTRICT"), index=True
    )

    # Worst flag severity (high / medium / low), None = no flags. Kept in step with
    # `flags` by _set_severity, so lists can filter and sort on it.
    severity: Mapped[str | None] = mapped_column(String(10), index=True)

    @validates("entries")
    def _check_entries(self, _key: str, entries: list[TimesheetEntry] | None) -> Any:
        """One entry per date, hours 0-24, sorted: checked when the days are set."""
        return check_entries(list(entries or []))

    @validates("flags")
    def _set_severity(self, _key: str, flags: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Every time the flags are set: add each flag's severity and keep the worst one."""
        enriched = with_severity(flags or [])
        self.severity = highest_severity(enriched)
        return enriched
