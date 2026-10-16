"""admin and reviewer roles only

Four roles become two:
  super_admin -> admin     (keeps full access, including user management)
  admin       -> admin
  reviewer    -> reviewer
  viewer      -> reviewer, DEACTIVATED (a read-only user must not silently gain the
                 right to approve pay; an admin reactivates them on purpose)
The roles super_admin and viewer are deleted, and a CHECK allows only the two names.

Downgrade puts the four roles back but cannot know who was a super admin or a
viewer before: everyone keeps admin / reviewer.

Revision ID: b7e41c2d9a05
Revises: 0fce3be575f3
Create Date: 2026-10-16 17:30:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e41c2d9a05"
down_revision: str | Sequence[str] | None = "0fce3be575f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "auth"


def upgrade() -> None:
    # The two roles that stay (normally already there; seeded at startup).
    op.execute(
        f"INSERT INTO {SCHEMA}.roles (name) VALUES ('admin'), ('reviewer') "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.users
        SET role_id = (SELECT id FROM {SCHEMA}.roles WHERE name = 'admin'),
            updated_at = now()
        WHERE role_id = (SELECT id FROM {SCHEMA}.roles WHERE name = 'super_admin')
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.users
        SET role_id = (SELECT id FROM {SCHEMA}.roles WHERE name = 'reviewer'),
            is_active = false,
            updated_at = now()
        WHERE role_id = (SELECT id FROM {SCHEMA}.roles WHERE name = 'viewer')
        """
    )
    op.execute(f"DELETE FROM {SCHEMA}.roles WHERE name IN ('super_admin', 'viewer')")
    op.create_check_constraint(
        op.f("ck_roles_name_known"),
        "roles",
        "name IN ('admin', 'reviewer')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_roles_name_known"), "roles", type_="check", schema=SCHEMA
    )
    op.execute(
        f"INSERT INTO {SCHEMA}.roles (name) VALUES ('super_admin'), ('viewer') "
        "ON CONFLICT (name) DO NOTHING"
    )
