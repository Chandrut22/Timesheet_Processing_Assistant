"""Holidays belong to one company: no more "all companies" holidays

- every holiday that applied to all companies (company_id IS NULL) is copied into each
  company (active or not), keeping its name, active state and audit columns; a company
  that already has its own holiday on that date keeps its own
- the "all companies" rows are deleted, company_id becomes NOT NULL
- the unique (company_id, holiday_date) no longer needs NULLS NOT DISTINCT

Pay is unchanged: a company's holiday dates are the same as before (its own + the ones
that were global), so recalculating an existing timesheet gives the same result.

Downgrade makes company_id nullable again and restores the old constraint, but it cannot
know which rows used to be "all companies": the copies stay one per company. Back up
first if that matters:  pg_dump -t core.holidays <database>

Revision ID: d5e9b3f7a1c2
Revises: c4d8a2e6f0b3
Create Date: 2026-10-28 12:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e9b3f7a1c2"
down_revision: str | Sequence[str] | None = "c4d8a2e6f0b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
UNIQUE = "uq_holidays_company_date"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.holidays
            (company_id, holiday_date, name, is_active, created_at, updated_at,
             created_by, updated_by)
        SELECT c.id, h.holiday_date, h.name, h.is_active, h.created_at, now(),
               h.created_by, h.updated_by
        FROM {SCHEMA}.holidays h
        CROSS JOIN {SCHEMA}.companies c
        WHERE h.company_id IS NULL
        ON CONFLICT ON CONSTRAINT {UNIQUE} DO NOTHING
        """
    )
    op.execute(f"DELETE FROM {SCHEMA}.holidays WHERE company_id IS NULL")
    op.alter_column("holidays", "company_id", nullable=False, schema=SCHEMA)
    op.drop_constraint(UNIQUE, "holidays", type_="unique", schema=SCHEMA)
    op.create_unique_constraint(
        UNIQUE, "holidays", ["company_id", "holiday_date"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint(UNIQUE, "holidays", type_="unique", schema=SCHEMA)
    op.create_unique_constraint(
        UNIQUE,
        "holidays",
        ["company_id", "holiday_date"],
        schema=SCHEMA,
        postgresql_nulls_not_distinct=True,
    )
    op.alter_column("holidays", "company_id", nullable=True, schema=SCHEMA)
