"""created_by / updated_by on every editable table; updated_at on holidays and senders

Adds the auth-service user UUID of whoever created and last changed each row
(NULL = the system: a Celery job, the email listener, or unknown for rows that
existed before this migration). No foreign key: users live in auth-service.

- companies, employees, submissions, documents, timesheets: created_by, updated_by
- holidays, whitelist_senders: also updated_at (existing rows: = created_at)
- export_batches: created_by_id renamed to created_by (data kept), updated_by added
- submissions: created_by filled from uploaded_by_id for uploads

All new columns allow NULL and have no default, so no table is rewritten.

Revision ID: e3a7c9d1f5b2
Revises: d8f2b4a6c1e3
Create Date: 2026-10-24 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a7c9d1f5b2"
down_revision: str | Sequence[str] | None = "d8f2b4a6c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"

BY_TABLES = (
    "companies",
    "employees",
    "holidays",
    "whitelist_senders",
    "submissions",
    "documents",
    "timesheets",
)
NEW_UPDATED_AT = ("holidays", "whitelist_senders")


def upgrade() -> None:
    for table in NEW_UPDATED_AT:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            schema=SCHEMA,
        )
        op.execute(f"UPDATE {SCHEMA}.{table} SET updated_at = created_at")

    for table in BY_TABLES:
        op.add_column(table, sa.Column("created_by", sa.Uuid(), nullable=True), schema=SCHEMA)
        op.add_column(table, sa.Column("updated_by", sa.Uuid(), nullable=True), schema=SCHEMA)

    op.alter_column("export_batches", "created_by_id", new_column_name="created_by", schema=SCHEMA)
    op.add_column(
        "export_batches", sa.Column("updated_by", sa.Uuid(), nullable=True), schema=SCHEMA
    )
    op.execute(f"UPDATE {SCHEMA}.export_batches SET updated_by = created_by")

    # Uploads already record who uploaded them.
    op.execute(
        f"UPDATE {SCHEMA}.submissions SET created_by = uploaded_by_id, updated_by = uploaded_by_id"
        " WHERE uploaded_by_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("export_batches", "updated_by", schema=SCHEMA)
    op.alter_column("export_batches", "created_by", new_column_name="created_by_id", schema=SCHEMA)
    for table in reversed(BY_TABLES):
        op.drop_column(table, "updated_by", schema=SCHEMA)
        op.drop_column(table, "created_by", schema=SCHEMA)
    for table in NEW_UPDATED_AT:
        op.drop_column(table, "updated_at", schema=SCHEMA)
