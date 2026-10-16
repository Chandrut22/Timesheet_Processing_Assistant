"""add reprocess runs

- reprocess_runs: who reprocessed, when, why, results before / after (never deleted)
- timesheets: version, reprocess_run_id (run that made it), superseded_by_id (newer
  version that replaced it); status "superseded" allowed
- processing_steps: reprocess_run_id, so the timeline can group steps by run
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7df861dff616"
down_revision: str | Sequence[str] | None = "b12e45bda29e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA = "core"
TS_STATUSES_OLD = "'needs_review', 'approved', 'rejected', 'exported'"
TS_STATUSES_NEW = "'needs_review', 'approved', 'rejected', 'exported', 'superseded'"


def upgrade() -> None:
    # --- reprocess_runs -------------------------------------------------------------
    op.create_table(
        "reprocess_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_name", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column(
            "before_result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("after_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name=op.f("ck_reprocess_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) >= 3", name=op.f("ck_reprocess_runs_reason_not_blank")
        ),
        sa.CheckConstraint(
            "(status = 'running') = (completed_at IS NULL)",
            name=op.f("ck_reprocess_runs_completion_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            [f"{SCHEMA}.submissions.id"],
            name=op.f("fk_reprocess_runs_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [f"{SCHEMA}.documents.id"],
            name=op.f("fk_reprocess_runs_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reprocess_runs")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reprocess_runs_submission",
        "reprocess_runs",
        ["submission_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "uq_reprocess_runs_one_running",
        "reprocess_runs",
        ["submission_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'running'"),
    )

    # --- timesheets -----------------------------------------------------------------
    op.add_column(
        "timesheets",
        sa.Column("version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("timesheets", sa.Column("reprocess_run_id", sa.Uuid()), schema=SCHEMA)
    op.add_column("timesheets", sa.Column("superseded_by_id", sa.Uuid()), schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_timesheets_reprocess_run_id_reprocess_runs"),
        "timesheets",
        "reprocess_runs",
        ["reprocess_run_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
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
        op.f("ix_core_timesheets_reprocess_run_id"),
        "timesheets",
        ["reprocess_run_id"],
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_version_positive"), "timesheets", "version >= 1", schema=SCHEMA
    )
    op.create_check_constraint(
        op.f("ck_timesheets_not_superseded_by_self"),
        "timesheets",
        "superseded_by_id IS NULL OR superseded_by_id <> id",
        schema=SCHEMA,
    )
    op.drop_constraint(op.f("ck_timesheets_status_valid"), "timesheets", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_timesheets_status_valid"),
        "timesheets",
        f"status IN ({TS_STATUSES_NEW})",
        schema=SCHEMA,
    )

    # --- processing_steps -----------------------------------------------------------
    op.add_column("processing_steps", sa.Column("reprocess_run_id", sa.Uuid()), schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_processing_steps_reprocess_run_id_reprocess_runs"),
        "processing_steps",
        "reprocess_runs",
        ["reprocess_run_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_processing_steps_reprocess_run",
        "processing_steps",
        ["reprocess_run_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("reprocess_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_processing_steps_reprocess_run", table_name="processing_steps", schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_processing_steps_reprocess_run_id_reprocess_runs"),
        "processing_steps",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("processing_steps", "reprocess_run_id", schema=SCHEMA)

    # Old versions cannot stay "superseded" without this migration: mark them rejected.
    op.execute(
        f"UPDATE {SCHEMA}.timesheets SET status = 'rejected', "
        "notes = coalesce(notes || ' ', '') || '[replaced by a reprocess]' "
        "WHERE status = 'superseded'"
    )
    op.drop_constraint(op.f("ck_timesheets_status_valid"), "timesheets", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_timesheets_status_valid"),
        "timesheets",
        f"status IN ({TS_STATUSES_OLD})",
        schema=SCHEMA,
    )
    op.drop_constraint(op.f("ck_timesheets_not_superseded_by_self"), "timesheets", schema=SCHEMA)
    op.drop_constraint(op.f("ck_timesheets_version_positive"), "timesheets", schema=SCHEMA)
    op.drop_index(
        op.f("ix_core_timesheets_reprocess_run_id"), table_name="timesheets", schema=SCHEMA
    )
    op.drop_constraint(
        op.f("fk_timesheets_superseded_by_id_timesheets"),
        "timesheets",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_timesheets_reprocess_run_id_reprocess_runs"),
        "timesheets",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("timesheets", "superseded_by_id", schema=SCHEMA)
    op.drop_column("timesheets", "reprocess_run_id", schema=SCHEMA)
    op.drop_column("timesheets", "version", schema=SCHEMA)

    op.drop_index("uq_reprocess_runs_one_running", table_name="reprocess_runs", schema=SCHEMA)
    op.drop_index("ix_reprocess_runs_submission", table_name="reprocess_runs", schema=SCHEMA)
    op.drop_table("reprocess_runs", schema=SCHEMA)
