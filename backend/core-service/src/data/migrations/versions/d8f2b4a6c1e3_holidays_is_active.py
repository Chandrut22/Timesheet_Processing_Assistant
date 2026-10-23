"""holidays.is_active: a holiday can be switched off without deleting it

Existing holidays stay active (server default true). An inactive holiday no longer
counts in pay from the next calculation. Downgrade drops the column.

Revision ID: d8f2b4a6c1e3
Revises: b5d9e3f7a2c4
Create Date: 2026-10-22 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f2b4a6c1e3"
down_revision: str | Sequence[str] | None = "b5d9e3f7a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column(
        "holidays",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("holidays", "is_active", schema=SCHEMA)
