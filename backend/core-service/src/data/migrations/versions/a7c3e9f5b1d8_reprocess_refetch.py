"""Reprocess can fetch the email again from the mailbox

- reprocess_runs.refetch: 'missing' | 'all' | NULL (nothing fetched: the saved text is used)
- processing_steps.step: allow 'fetch' (the reprocess's "Fetch from mailbox" step)

Revision ID: a7c3e9f5b1d8
Revises: e3a7c9d1f5b2
Create Date: 2026-10-27 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9f5b1d8"
down_revision: str | Sequence[str] | None = "e3a7c9d1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
STEP_CHECK = "ck_processing_steps_step_valid"
STEPS_OLD = "'collect', 'read', 'classify', 'extract', 'match', 'rules', 'decide', 'pipeline'"
STEPS_NEW = (
    "'collect', 'fetch', 'read', 'classify', 'extract', 'match', 'rules', 'decide', 'pipeline'"
)
REFETCH_CHECK = "ck_reprocess_runs_refetch_valid"


def upgrade() -> None:
    op.add_column(
        "reprocess_runs", sa.Column("refetch", sa.String(length=10), nullable=True), schema=SCHEMA
    )
    op.create_check_constraint(
        op.f(REFETCH_CHECK), "reprocess_runs", "refetch IN ('missing', 'all')", schema=SCHEMA
    )
    op.drop_constraint(op.f(STEP_CHECK), "processing_steps", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        op.f(STEP_CHECK), "processing_steps", f"step IN ({STEPS_NEW})", schema=SCHEMA
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.processing_steps WHERE step = 'fetch'")
    op.drop_constraint(op.f(STEP_CHECK), "processing_steps", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        op.f(STEP_CHECK), "processing_steps", f"step IN ({STEPS_OLD})", schema=SCHEMA
    )
    op.drop_constraint(op.f(REFETCH_CHECK), "reprocess_runs", type_="check", schema=SCHEMA)
    op.drop_column("reprocess_runs", "refetch", schema=SCHEMA)
