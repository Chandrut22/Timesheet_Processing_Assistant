"""documents: how a file was read, and what kind of writing a photo / scan has

- read_method: docling / plain / vision (NULL for documents read before this)
- unclear_marks: [UNCLEAR] marks the vision model left (default 0)
- writing_class: printed_only / handwritten_only / mixed / no_text / uncertain
  (NULL for typed documents), writing_confidence (0-1), has_handwritten_hours (default
  false), writing_reason (short, from visible evidence)

All nullable or with a default: existing rows need no rewrite. Downgrade drops them.

Revision ID: b5d9e3f7a2c4
Revises: f4a8c2e6b9d1
Create Date: 2026-10-22 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d9e3f7a2c4"
down_revision: str | Sequence[str] | None = "f4a8c2e6b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
READ_METHODS = "'docling', 'plain', 'vision'"
WRITING_CLASSES = "'printed_only', 'handwritten_only', 'mixed', 'no_text', 'uncertain'"


def upgrade() -> None:
    op.add_column("documents", sa.Column("read_method", sa.String(10)), schema=SCHEMA)
    op.add_column(
        "documents",
        sa.Column("unclear_marks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("documents", sa.Column("writing_class", sa.String(20)), schema=SCHEMA)
    op.add_column("documents", sa.Column("writing_confidence", sa.Numeric(3, 2)), schema=SCHEMA)
    op.add_column(
        "documents",
        sa.Column("has_handwritten_hours", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("documents", sa.Column("writing_reason", sa.String(300)), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_documents_read_method_valid"),
        "documents",
        f"read_method IN ({READ_METHODS})",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_documents_unclear_marks_non_negative"),
        "documents",
        "unclear_marks >= 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_documents_writing_class_valid"),
        "documents",
        f"writing_class IN ({WRITING_CLASSES})",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_documents_writing_confidence_range"),
        "documents",
        "writing_confidence IS NULL OR (writing_confidence >= 0 AND writing_confidence <= 1)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    for name in (
        "writing_confidence_range",
        "writing_class_valid",
        "unclear_marks_non_negative",
        "read_method_valid",
    ):
        op.drop_constraint(op.f(f"ck_documents_{name}"), "documents", schema=SCHEMA)
    for column in (
        "writing_reason",
        "has_handwritten_hours",
        "writing_confidence",
        "writing_class",
        "unclear_marks",
        "read_method",
    ):
        op.drop_column("documents", column, schema=SCHEMA)
