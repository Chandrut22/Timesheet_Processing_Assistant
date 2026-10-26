"""users.created_by / updated_by: which user created and last changed each user

Self-references to auth.users.id (ON DELETE SET NULL). NULL = the system (the seed
script) or unknown for users that existed before this migration.

Revision ID: c4f8a2e6b1d3
Revises: b7e41c2d9a05
Create Date: 2026-10-24 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f8a2e6b1d3"
down_revision: str | Sequence[str] | None = "b7e41c2d9a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "auth"


def upgrade() -> None:
    for column in ("created_by", "updated_by"):
        op.add_column(
            "users", sa.Column(column, sa.Uuid(), nullable=True), schema=SCHEMA
        )
        op.create_foreign_key(
            f"fk_users_{column}_users",
            "users",
            "users",
            [column],
            ["id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for column in ("updated_by", "created_by"):
        op.drop_constraint(
            f"fk_users_{column}_users", "users", schema=SCHEMA, type_="foreignkey"
        )
        op.drop_column("users", column, schema=SCHEMA)
