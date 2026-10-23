"""Timesheet days as JSONB, version history table, no more superseded timesheets

1. timesheets.entries (JSONB array) replaces the timesheet_entries table. Every day is
   copied over, in date order, with all its fields.
2. timesheet_versions keeps earlier versions of a timesheet (for history / rollback).
3. A reprocess now updates the timesheet in place, so status "superseded" and
   superseded_by_id go. Existing superseded timesheets are moved into the history of
   the timesheet that replaced them (following the chain to the live one), as the
   version they were, change "reprocessed". One that nothing replaced (or that clashes
   with another old version of the same timesheet) stays as a rejected timesheet with
   the removed_by_reprocess flag. Nothing is lost.

Downgrade: the timesheet_entries table, superseded_by_id and the "superseded" status
come back with the days copied back. The version history cannot be turned back into
superseded rows: it is dropped (the current timesheets stay as they are).

Revision ID: f4a8c2e6b9d1
Revises: d2f6a4b8c3e5
Create Date: 2026-10-22 18:00:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f4a8c2e6b9d1"
down_revision: str | Sequence[str] | None = "d2f6a4b8c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
STATUSES_NEW = "'needs_review', 'approved', 'rejected', 'exported'"
STATUSES_OLD = "'needs_review', 'approved', 'rejected', 'exported', 'superseded'"
CHANGES = (
    "'entries_edited', 'employee_matched', 'week_changed', 'recalculated', "
    "'reprocessed', 'rolled_back'"
)

# The snapshot of a timesheet (same fields as src/core/services/version_history.py,
# copied here so the migration never changes when the app code does).
SNAPSHOT_COLUMNS = (
    "company_id",
    "employee_id",
    "reviewed_by_id",
    "week_start",
    "reviewed_at",
    "regular_hours",
    "overtime_hours",
    "double_time_hours",
    "holiday_hours",
    "stated_total",
    "email_stated_total",
    "read_confidence",
    "confidence",
    "hourly_rate",
    "overtime_rate",
    "double_time_rate",
    "holiday_rate",
    "regular_amount",
    "overtime_amount",
    "double_time_amount",
    "holiday_amount",
    "extracted_name",
    "extracted_code",
    "extracted_company_name",
    "status",
    "currency",
    "match_method",
    "match_reason",
    "notes",
    "reviewed_by_name",
)
REMOVED_FLAG = {
    "code": "removed_by_reprocess",
    "message": "Replaced by a reprocess before version history existed, and no newer "
    "version was linked to it. Kept for the record.",
    "severity": "low",
}


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, list, dict)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)  # UUID, Decimal (as text: nothing is rounded)


def _snapshot(row: Any) -> dict[str, Any]:
    snap = {name: _plain(getattr(row, name)) for name in SNAPSHOT_COLUMNS}
    if snap["status"] == "superseded":  # what it was before it was replaced
        snap["status"] = "needs_review"
    snap["flags"] = row.flags or []
    snap["entries"] = row.entries or []
    return snap


def upgrade() -> None:
    # --- 1. the days move onto the timesheet --------------------------------------------
    op.add_column(
        "timesheets",
        sa.Column(
            "entries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.timesheets AS t
        SET entries = d.days
        FROM (
            SELECT timesheet_id,
                   jsonb_agg(
                       jsonb_build_object(
                           'work_date', to_char(work_date, 'YYYY-MM-DD'),
                           'hours', hours,
                           'is_holiday', is_holiday,
                           'sheet_holiday', sheet_holiday,
                           'double_time_marked', double_time_marked,
                           'note', note
                       )
                       ORDER BY work_date
                   ) AS days
            FROM {SCHEMA}.timesheet_entries
            GROUP BY timesheet_id
        ) AS d
        WHERE d.timesheet_id = t.id
        """
    )
    op.create_check_constraint(
        op.f("ck_timesheets_entries_is_array"),
        "timesheets",
        "jsonb_typeof(entries) = 'array'",
        schema=SCHEMA,
    )

    # --- 2. the version history -----------------------------------------------------------
    op.create_table(
        "timesheet_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("timesheet_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("change", sa.String(length=30), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=True),
        sa.Column("changed_by_name", sa.String(length=150), nullable=True),
        sa.Column("reprocess_run_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_timesheet_versions_version_positive")),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'",
            name=op.f("ck_timesheet_versions_snapshot_is_object"),
        ),
        sa.CheckConstraint(
            f"change IN ({CHANGES})", name=op.f("ck_timesheet_versions_change_valid")
        ),
        sa.ForeignKeyConstraint(
            ["timesheet_id"],
            [f"{SCHEMA}.timesheets.id"],
            name=op.f("fk_timesheet_versions_timesheet_id_timesheets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reprocess_run_id"],
            [f"{SCHEMA}.reprocess_runs.id"],
            name=op.f("fk_timesheet_versions_reprocess_run_id_reprocess_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timesheet_versions")),
        sa.UniqueConstraint("timesheet_id", "version", name="uq_timesheet_versions_version"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_core_timesheet_versions_timesheet_id"),
        "timesheet_versions",
        ["timesheet_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_core_timesheet_versions_reprocess_run_id"),
        "timesheet_versions",
        ["reprocess_run_id"],
        unique=False,
        schema=SCHEMA,
    )

    # --- 3. superseded timesheets become versions of the one that replaced them ----------
    _move_superseded_into_history(op.get_bind())

    op.drop_constraint(
        op.f("fk_timesheets_superseded_by_id_timesheets"), "timesheets", schema=SCHEMA
    )
    op.drop_index(
        op.f("ix_core_timesheets_superseded_by_id"), table_name="timesheets", schema=SCHEMA
    )
    op.drop_constraint(op.f("ck_timesheets_not_superseded_by_self"), "timesheets", schema=SCHEMA)
    op.drop_column("timesheets", "superseded_by_id", schema=SCHEMA)
    op.drop_constraint(op.f("ck_timesheets_status_valid"), "timesheets", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_timesheets_status_valid"),
        "timesheets",
        f"status IN ({STATUSES_NEW})",
        schema=SCHEMA,
    )

    op.drop_table("timesheet_entries", schema=SCHEMA)


def _move_superseded_into_history(conn: sa.engine.Connection) -> None:
    rows = conn.execute(
        sa.text(
            f"SELECT t.*, r.requested_by_id, r.requested_by_name, r.reason AS run_reason "
            f"FROM {SCHEMA}.timesheets t "
            f"LEFT JOIN {SCHEMA}.timesheets s ON s.id = t.superseded_by_id "
            f"LEFT JOIN {SCHEMA}.reprocess_runs r ON r.id = s.reprocess_run_id"
        )
    ).all()
    by_id = {row.id: row for row in rows}
    taken: set[tuple[Any, int]] = set()  # (timesheet, version) already in the history

    def live_successor(row: Any) -> Any | None:
        seen = set()
        current = row
        while current is not None and current.status == "superseded":
            if current.id in seen or current.superseded_by_id is None:
                return None
            seen.add(current.id)
            current = by_id.get(current.superseded_by_id)
        return current

    moved: list[Any] = []
    for row in sorted(rows, key=lambda r: (r.version, r.created_at)):
        if row.status != "superseded":
            continue
        target = live_successor(row)
        key = (target.id, row.version) if target is not None else None
        if target is None or key in taken or row.version >= target.version:
            conn.execute(
                sa.text(
                    f"UPDATE {SCHEMA}.timesheets SET status = 'rejected', "
                    "reviewed_at = COALESCE(reviewed_at, updated_at, now()), "
                    "notes = COALESCE(notes, 'Replaced by a reprocess (no newer version linked).'), "
                    "flags = flags || CAST(:flag AS jsonb), "
                    "severity = COALESCE(severity, 'low') WHERE id = :id"
                ),
                {"id": row.id, "flag": json.dumps([REMOVED_FLAG])},
            )
            continue
        taken.add(key)
        replacing = by_id[row.superseded_by_id]
        conn.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.timesheet_versions (timesheet_id, version, change, "
                "changed_by_id, changed_by_name, reprocess_run_id, reason, snapshot, created_at) "
                "VALUES (:timesheet_id, :version, 'reprocessed', :by_id, :by_name, :run_id, "
                ":reason, CAST(:snapshot AS jsonb), :created_at)"
            ),
            {
                "timesheet_id": target.id,
                "version": row.version,
                "by_id": row.requested_by_id,
                "by_name": row.requested_by_name,
                "run_id": replacing.reprocess_run_id,
                "reason": row.run_reason,
                "snapshot": json.dumps(_snapshot(row)),
                "created_at": replacing.created_at,
            },
        )
        moved.append(row.id)
    if moved:
        conn.execute(
            sa.text(f"DELETE FROM {SCHEMA}.timesheets WHERE id = ANY(:ids)"), {"ids": moved}
        )


def downgrade() -> None:
    op.create_table(
        "timesheet_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("timesheet_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("is_holiday", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "double_time_marked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("sheet_holiday", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "hours >= 0 AND hours <= 24", name=op.f("ck_timesheet_entries_hours_range")
        ),
        sa.ForeignKeyConstraint(
            ["timesheet_id"],
            [f"{SCHEMA}.timesheets.id"],
            name=op.f("fk_timesheet_entries_timesheet_id_timesheets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timesheet_entries")),
        sa.UniqueConstraint("timesheet_id", "work_date", name="uq_timesheet_entries_day"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_core_timesheet_entries_timesheet_id"),
        "timesheet_entries",
        ["timesheet_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.timesheet_entries
            (timesheet_id, work_date, hours, is_holiday, sheet_holiday, double_time_marked, note)
        SELECT t.id, d.work_date, d.hours, COALESCE(d.is_holiday, false),
               COALESCE(d.sheet_holiday, false), COALESCE(d.double_time_marked, false), d.note
        FROM {SCHEMA}.timesheets t,
             jsonb_to_recordset(t.entries) AS d(
                 work_date date, hours numeric, is_holiday boolean, sheet_holiday boolean,
                 double_time_marked boolean, note varchar
             )
        """
    )

    op.drop_constraint(op.f("ck_timesheets_status_valid"), "timesheets", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_timesheets_status_valid"),
        "timesheets",
        f"status IN ({STATUSES_OLD})",
        schema=SCHEMA,
    )
    op.add_column("timesheets", sa.Column("superseded_by_id", sa.Uuid()), schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_timesheets_superseded_by_id_timesheets"),
        "timesheets",
        "timesheets",
        ["superseded_by_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_core_timesheets_superseded_by_id"),
        "timesheets",
        ["superseded_by_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_not_superseded_by_self"),
        "timesheets",
        "superseded_by_id IS NULL OR superseded_by_id <> id",
        schema=SCHEMA,
    )

    op.drop_index(
        op.f("ix_core_timesheet_versions_reprocess_run_id"),
        table_name="timesheet_versions",
        schema=SCHEMA,
    )
    op.drop_index(
        op.f("ix_core_timesheet_versions_timesheet_id"),
        table_name="timesheet_versions",
        schema=SCHEMA,
    )
    op.drop_table("timesheet_versions", schema=SCHEMA)
    op.drop_constraint(op.f("ck_timesheets_entries_is_array"), "timesheets", schema=SCHEMA)
    op.drop_column("timesheets", "entries", schema=SCHEMA)
