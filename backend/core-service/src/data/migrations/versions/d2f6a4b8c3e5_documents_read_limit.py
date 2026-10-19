"""documents.read_limit: which pages / sheets of a big file were not read

NULL = the document was read in full (all rows before this change, too).

Revision ID: d2f6a4b8c3e5
Revises: c9e5f3a7b2d4
Create Date: 2026-10-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2f6a4b8c3e5"
down_revision: str | Sequence[str] | None = "c9e5f3a7b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("read_limit", postgresql.JSONB(astext_type=sa.Text())),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("documents", "read_limit", schema=SCHEMA)
