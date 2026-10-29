"""add timesheet severity

Revision ID: 9e39c43cfd52
Revises: d33caba62e7a
Create Date: 2026-10-15 14:39:06.695880

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.constants.flags import highest_severity, with_severity

# revision identifiers, used by Alembic.
revision: str = "9e39c43cfd52"
down_revision: str | Sequence[str] | None = "d33caba62e7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column(
        "timesheets",
        sa.Column("severity", sa.String(length=10), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_severity_valid"),
        "timesheets",
        "severity IN ('high', 'medium', 'low')",
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_core_timesheets_severity"), "timesheets", ["severity"], schema=SCHEMA
    )

    # Backfill: add "severity" to each stored flag and set the column.
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, flags FROM {SCHEMA}.timesheets")).all()
    for row_id, flags in rows:
        enriched = with_severity(flags or [])
        conn.execute(
            sa.text(
                f"UPDATE {SCHEMA}.timesheets "
                "SET flags = CAST(:flags AS jsonb), severity = :severity WHERE id = :id"
            ),
            {
                "flags": json.dumps(enriched),
                "severity": highest_severity(enriched),
                "id": row_id,
            },
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_core_timesheets_severity"), table_name="timesheets", schema=SCHEMA
    )
    op.drop_constraint(
        op.f("ck_timesheets_severity_valid"), "timesheets", type_="check", schema=SCHEMA
    )
    op.drop_column("timesheets", "severity", schema=SCHEMA)
