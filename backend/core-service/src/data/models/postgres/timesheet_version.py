"""Earlier versions of a timesheet, so changes can be seen and rolled back.

A reprocess or "Create as new version" first saves the timesheet as it was into this
table under its number, then gives it the next free number; `change` says what made
that next version. Restoring version N saves what the timesheet had under its own
number and gives it N's data and number back (no new number). The current version is
the timesheet itself; its row here, if any, is refreshed when it is left (Save edits
in place). Rows are never deleted (they go only with their timesheet)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.timesheet_status import TimesheetChange
from src.data.models.postgres.base import SCHEMA, Base, UUIDPrimaryKeyMixin, enum_check


class TimesheetVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "timesheet_versions"
    __table_args__ = (
        UniqueConstraint(
            "timesheet_id", "version", name="uq_timesheet_versions_version"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("jsonb_typeof(snapshot) = 'object'", name="snapshot_is_object"),
        enum_check("change", TimesheetChange),
    )

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.timesheets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(SmallInteger)  # the version this snapshot IS
    change: Mapped[str] = mapped_column(String(30))  # what made the next version
    # Who made the next version (auth-service user: id + name, no foreign key).
    # None = the system (a reprocess keeps the name of the person who asked for it).
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    changed_by_name: Mapped[str | None] = mapped_column(String(150))
    reprocess_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.reprocess_runs.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str | None] = mapped_column(
        Text
    )  # a rollback's or reprocess's reason
    # The timesheet's data at this version (version_history.SNAPSHOT_FIELDS + entries).
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
