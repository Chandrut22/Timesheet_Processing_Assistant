"""worker retries, integrity checks, indexes

- submissions: attempts / retry_at / retry_token (worker retries after a temporary
  failure); processed rows always have processed_at
- timesheets: hours never negative; approved / rejected / exported always have a
  decision time; exported always points to its export batch
- documents, processing_steps, export_batches, audit_events: basic value checks
- indexes for the review list (received_at, week_start, flags) and for foreign keys
  that had none (superseded_by_id, processing_steps / reprocess_runs document_id)
- existing rows are filled in first (decision / export / processed times) so the
  checks hold

Revision ID: 944efa68233f
Revises: c9deb1fe0307
Create Date: 2026-10-16 15:47:37.672115

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "944efa68233f"
down_revision: str | Sequence[str] | None = "c9deb1fe0307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"

CHECKS: list[tuple[str, str, str]] = [
    # (table, name, condition)
    ("submissions", "attempts_non_negative", "attempts >= 0"),
    ("submissions", "retry_fields_together", "(retry_at IS NULL) = (retry_token IS NULL)"),
    ("submissions", "processed_has_time", "status <> 'processed' OR processed_at IS NOT NULL"),
    (
        "timesheets",
        "hours_non_negative",
        "regular_hours >= 0 AND overtime_hours >= 0 AND double_time_hours >= 0 "
        "AND holiday_hours >= 0 AND (stated_total IS NULL OR stated_total >= 0)",
    ),
    (
        "timesheets",
        "decided_has_time",
        "status NOT IN ('approved', 'rejected', 'exported') OR reviewed_at IS NOT NULL",
    ),
    (
        "timesheets",
        "exported_has_batch",
        "status <> 'exported' OR (export_batch_id IS NOT NULL AND exported_at IS NOT NULL)",
    ),
    ("documents", "size_non_negative", "size_bytes >= 0"),
    ("documents", "sha256_format", "sha256 ~ '^[0-9a-f]{64}$'"),
    ("processing_steps", "duration_non_negative", "duration_ms >= 0"),
    ("export_batches", "week_range", "week_end >= week_start"),
    ("export_batches", "row_count_non_negative", "row_count >= 0"),
    (
        "export_batches",
        "hours_non_negative",
        "regular_hours >= 0 AND overtime_hours >= 0 AND double_time_hours >= 0 "
        "AND holiday_hours >= 0",
    ),
    (
        "export_batches",
        "amounts_non_negative",
        "regular_amount >= 0 AND overtime_amount >= 0 AND double_time_amount >= 0 "
        "AND holiday_amount >= 0 AND gross_amount >= 0",
    ),
    ("audit_events", "action_not_blank", "length(btrim(action)) > 0"),
]


def upgrade() -> None:
    # --- submissions: retry bookkeeping -----------------------------------------------
    op.add_column(
        "submissions",
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("submissions", sa.Column("retry_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("submissions", sa.Column("retry_token", sa.Uuid()), schema=SCHEMA)

    # --- fill in existing rows so the new checks hold --------------------------------
    op.execute(
        f"UPDATE {SCHEMA}.submissions SET attempts = 1 WHERE status IN ('processed', 'failed')"
    )
    op.execute(
        f"UPDATE {SCHEMA}.submissions SET processed_at = updated_at "
        "WHERE status = 'processed' AND processed_at IS NULL"
    )
    op.execute(
        f"UPDATE {SCHEMA}.timesheets SET reviewed_at = updated_at "
        "WHERE status IN ('approved', 'rejected', 'exported') AND reviewed_at IS NULL"
    )
    op.execute(
        f"UPDATE {SCHEMA}.timesheets SET exported_at = updated_at "
        "WHERE status = 'exported' AND exported_at IS NULL"
    )

    # --- checks ------------------------------------------------------------------------
    for table, name, condition in CHECKS:
        op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, condition, schema=SCHEMA)

    # --- indexes -----------------------------------------------------------------------
    op.create_index(
        op.f("ix_core_submissions_received_at"), "submissions", ["received_at"], schema=SCHEMA
    )
    op.create_index(
        op.f("ix_core_timesheets_superseded_by_id"),
        "timesheets",
        ["superseded_by_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_timesheets_week_start", "timesheets", ["week_start"], schema=SCHEMA)
    op.create_index(
        "ix_timesheets_flags",
        "timesheets",
        ["flags"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"flags": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_processing_steps_document",
        "processing_steps",
        ["document_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("document_id IS NOT NULL"),
    )
    op.create_index(
        "ix_reprocess_runs_document",
        "reprocess_runs",
        ["document_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("document_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_reprocess_runs_document", table_name="reprocess_runs", schema=SCHEMA)
    op.drop_index("ix_processing_steps_document", table_name="processing_steps", schema=SCHEMA)
    op.drop_index("ix_timesheets_flags", table_name="timesheets", schema=SCHEMA)
    op.drop_index("ix_timesheets_week_start", table_name="timesheets", schema=SCHEMA)
    op.drop_index(
        op.f("ix_core_timesheets_superseded_by_id"), table_name="timesheets", schema=SCHEMA
    )
    op.drop_index(op.f("ix_core_submissions_received_at"), table_name="submissions", schema=SCHEMA)
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check", schema=SCHEMA)
    for column in ("retry_token", "retry_at", "attempts"):
        op.drop_column("submissions", column, schema=SCHEMA)
