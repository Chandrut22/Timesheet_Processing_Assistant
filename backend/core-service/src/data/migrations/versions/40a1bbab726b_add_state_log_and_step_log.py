"""add state log and step log

Revision ID: 40a1bbab726b
Revises: 9e39c43cfd52
Create Date: 2026-10-15 15:49:41.889591

- submissions.state + state_reason (what people see), and "ignored" as a status
- submission_state_changes: every state change with its time
- processing_steps: the step-by-step log
- existing submissions get a state worked out from their timesheets
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from src.core.services.activity_log import state_from_timesheets

# revision identifiers, used by Alembic.
revision: str = "40a1bbab726b"
down_revision: str | Sequence[str] | None = "9e39c43cfd52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
STATES = (
    "'received', 'reading', 'matching', 'rule_checks', 'awaiting_review', 'approved', "
    "'rejected', 'exported', 'ignored', 'failed', 'reprocessing'"
)


def upgrade() -> None:
    # --- submissions: ignored status + state columns ------------------------------
    op.drop_constraint(op.f("ck_submissions_status_valid"), "submissions", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_submissions_status_valid"),
        "submissions",
        "status IN ('received', 'processing', 'processed', 'failed', 'ignored')",
        schema=SCHEMA,
    )
    op.add_column(
        "submissions",
        sa.Column("state", sa.String(length=20), nullable=False, server_default="received"),
        schema=SCHEMA,
    )
    op.add_column("submissions", sa.Column("state_reason", sa.Text(), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_submissions_state_valid"), "submissions", f"state IN ({STATES})", schema=SCHEMA
    )
    op.create_index(op.f("ix_core_submissions_state"), "submissions", ["state"], schema=SCHEMA)

    # --- state log -------------------------------------------------------------------
    op.create_table(
        "submission_state_changes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=20), nullable=True),
        sa.Column("to_state", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=150), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"to_state IN ({STATES})", name=op.f("ck_submission_state_changes_to_state_valid")
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            [f"{SCHEMA}.submissions.id"],
            name=op.f("fk_submission_state_changes_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_state_changes")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_submission_state_changes_submission",
        "submission_state_changes",
        ["submission_id", "created_at"],
        schema=SCHEMA,
    )

    # --- step log --------------------------------------------------------------------
    op.create_table(
        "processing_steps",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("timesheet_id", sa.Uuid(), nullable=True),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column("result", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "step IN ('collect', 'read', 'extract', 'match', 'rules', 'decide', 'pipeline')",
            name=op.f("ck_processing_steps_step_valid"),
        ),
        sa.CheckConstraint(
            "result IN ('success', 'warning', 'error')",
            name=op.f("ck_processing_steps_result_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            [f"{SCHEMA}.documents.id"],
            name=op.f("fk_processing_steps_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            [f"{SCHEMA}.submissions.id"],
            name=op.f("fk_processing_steps_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_steps")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_processing_steps_submission",
        "processing_steps",
        ["submission_id", "created_at"],
        schema=SCHEMA,
    )

    # --- backfill: a state for every existing submission -----------------------------
    conn = op.get_bind()
    submissions = conn.execute(sa.text(f"SELECT id, status, error FROM {SCHEMA}.submissions")).all()
    for submission_id, status, error in submissions:
        reason: str | None = None
        if status == "failed":
            state, reason = "failed", error
        elif status in ("received", "processing"):
            state = "received"
        else:
            statuses = (
                conn.execute(
                    sa.text(f"SELECT status FROM {SCHEMA}.timesheets WHERE submission_id = :id"),
                    {"id": submission_id},
                )
                .scalars()
                .all()
            )
            found = state_from_timesheets(statuses)
            if found is not None:
                state = found.value
            else:
                failed_doc = conn.execute(
                    sa.text(
                        f"SELECT error FROM {SCHEMA}.documents "
                        "WHERE submission_id = :id AND status = 'failed' LIMIT 1"
                    ),
                    {"id": submission_id},
                ).first()
                if failed_doc is not None:
                    state, reason = "failed", failed_doc[0]
                else:
                    state, reason = "ignored", "No timesheet found in this email or upload."
        conn.execute(
            sa.text(
                f"UPDATE {SCHEMA}.submissions SET state = :state, state_reason = :reason "
                "WHERE id = :id"
            ),
            {"state": state, "reason": reason, "id": submission_id},
        )
        conn.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.submission_state_changes "
                "(submission_id, from_state, to_state, reason) VALUES (:id, NULL, :state, :reason)"
            ),
            {"id": submission_id, "state": state, "reason": reason or "State log started"},
        )


def downgrade() -> None:
    op.drop_index("ix_processing_steps_submission", table_name="processing_steps", schema=SCHEMA)
    op.drop_table("processing_steps", schema=SCHEMA)
    op.drop_index(
        "ix_submission_state_changes_submission",
        table_name="submission_state_changes",
        schema=SCHEMA,
    )
    op.drop_table("submission_state_changes", schema=SCHEMA)
    op.drop_index(op.f("ix_core_submissions_state"), table_name="submissions", schema=SCHEMA)
    op.drop_constraint(op.f("ck_submissions_state_valid"), "submissions", schema=SCHEMA)
    op.drop_column("submissions", "state_reason", schema=SCHEMA)
    op.drop_column("submissions", "state", schema=SCHEMA)
    op.execute(f"DELETE FROM {SCHEMA}.submissions WHERE status = 'ignored'")
    op.drop_constraint(op.f("ck_submissions_status_valid"), "submissions", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_submissions_status_valid"),
        "submissions",
        "status IN ('received', 'processing', 'processed', 'failed')",
        schema=SCHEMA,
    )
