"""add matching and rule fields

- employees: assignment_start / assignment_end (outside_assignment rule)
- timesheets: extracted_company_name (company as written), email_stated_total
  (conflicting_hours rule), read_confidence (how well it was read; confidence is now
  the lower of reading and match confidence), match_reason (plain sentence)
- existing timesheets: read_confidence = their current confidence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9deb1fe0307"
down_revision: str | Sequence[str] | None = "7df861dff616"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    # --- employees ------------------------------------------------------------------
    op.add_column("employees", sa.Column("assignment_start", sa.Date()), schema=SCHEMA)
    op.add_column("employees", sa.Column("assignment_end", sa.Date()), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_employees_assignment_dates"),
        "employees",
        "assignment_end IS NULL OR assignment_start IS NULL OR assignment_end >= assignment_start",
        schema=SCHEMA,
    )

    # --- timesheets -----------------------------------------------------------------
    op.add_column(
        "timesheets",
        sa.Column("extracted_company_name", sa.String(length=200)),
        schema=SCHEMA,
    )
    op.add_column(
        "timesheets", sa.Column("email_stated_total", sa.Numeric(6, 2)), schema=SCHEMA
    )
    op.add_column(
        "timesheets", sa.Column("read_confidence", sa.Numeric(3, 2)), schema=SCHEMA
    )
    op.add_column("timesheets", sa.Column("match_reason", sa.Text()), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_timesheets_email_stated_total_non_negative"),
        "timesheets",
        "email_stated_total IS NULL OR email_stated_total >= 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_read_confidence_range"),
        "timesheets",
        "read_confidence IS NULL OR (read_confidence >= 0 AND read_confidence <= 1)",
        schema=SCHEMA,
    )
    # Until now `confidence` was the reading confidence: keep it as such.
    op.execute(f"UPDATE {SCHEMA}.timesheets SET read_confidence = confidence")
    # A short reason for timesheets matched before this change.
    op.execute(
        f"""
        UPDATE {SCHEMA}.timesheets t
        SET match_reason = 'Matched ' || e.full_name || ' (' || e.employee_code || ') by '
            || coalesce(t.match_method, 'unknown method') || '.'
        FROM {SCHEMA}.employees e
        WHERE t.employee_id = e.id AND t.match_reason IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_timesheets_read_confidence_range"), "timesheets", schema=SCHEMA
    )
    op.drop_constraint(
        op.f("ck_timesheets_email_stated_total_non_negative"),
        "timesheets",
        schema=SCHEMA,
    )
    for column in (
        "match_reason",
        "read_confidence",
        "email_stated_total",
        "extracted_company_name",
    ):
        op.drop_column("timesheets", column, schema=SCHEMA)
    op.drop_constraint(
        op.f("ck_employees_assignment_dates"), "employees", schema=SCHEMA
    )
    op.drop_column("employees", "assignment_end", schema=SCHEMA)
    op.drop_column("employees", "assignment_start", schema=SCHEMA)
