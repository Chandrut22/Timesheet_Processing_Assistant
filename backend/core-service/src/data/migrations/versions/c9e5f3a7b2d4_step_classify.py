"""processing_steps.step: allow 'classify' (the optional attachment classifier)

Revision ID: c9e5f3a7b2d4
Revises: b8d4e2f6a1c3
Create Date: 2026-10-18 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e5f3a7b2d4"
down_revision: str | Sequence[str] | None = "b8d4e2f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
NAME = "ck_processing_steps_step_valid"
OLD = "'collect', 'read', 'extract', 'match', 'rules', 'decide', 'pipeline'"
NEW = "'collect', 'read', 'classify', 'extract', 'match', 'rules', 'decide', 'pipeline'"


def upgrade() -> None:
    op.drop_constraint(op.f(NAME), "processing_steps", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        op.f(NAME), "processing_steps", f"step IN ({NEW})", schema=SCHEMA
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.processing_steps WHERE step = 'classify'")
    op.drop_constraint(op.f(NAME), "processing_steps", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        op.f(NAME), "processing_steps", f"step IN ({OLD})", schema=SCHEMA
    )
