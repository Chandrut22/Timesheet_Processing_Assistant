"""processing_steps.trace_id: the OpenTelemetry trace each step ran in

Lets the timeline link every step to its trace in Jaeger. NULL when tracing is off,
and for all steps written before this change.

Revision ID: b8d4e2f6a1c3
Revises: a7c3d9e1f2b4
Create Date: 2026-10-18 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d4e2f6a1c3"
down_revision: str | Sequence[str] | None = "a7c3d9e1f2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column("processing_steps", sa.Column("trace_id", sa.String(length=32)), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("processing_steps", "trace_id", schema=SCHEMA)
