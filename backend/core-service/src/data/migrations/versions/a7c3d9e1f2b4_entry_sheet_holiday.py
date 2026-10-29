"""timesheet_entries.sheet_holiday: holiday marked on the sheet, kept apart from the calendar

Until now recalculate() wrote "sheet OR calendar" back into is_holiday, so a day stayed
a holiday after the calendar holiday was deleted. sheet_holiday keeps what the sheet
(or a reviewer) said; is_holiday is recomputed from it on every recalculation.

Existing rows: a day that is a holiday but not in the calendar can only have come
from the sheet, so it gets sheet_holiday = true. Days that are in the calendar are
treated as calendar holidays.

Revision ID: a7c3d9e1f2b4
Revises: 944efa68233f
Create Date: 2026-10-18 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3d9e1f2b4"
down_revision: str | Sequence[str] | None = "944efa68233f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"


def upgrade() -> None:
    op.add_column(
        "timesheet_entries",
        sa.Column(
            "sheet_holiday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.timesheet_entries AS e
        SET sheet_holiday = true
        FROM {SCHEMA}.timesheets AS t
        WHERE e.timesheet_id = t.id
          AND e.is_holiday
          AND NOT EXISTS (
              SELECT 1 FROM {SCHEMA}.holidays AS h
              WHERE h.holiday_date = e.work_date
                AND (h.company_id IS NULL OR h.company_id = t.company_id)
          )
        """
    )


def downgrade() -> None:
    op.drop_column("timesheet_entries", "sheet_holiday", schema=SCHEMA)
