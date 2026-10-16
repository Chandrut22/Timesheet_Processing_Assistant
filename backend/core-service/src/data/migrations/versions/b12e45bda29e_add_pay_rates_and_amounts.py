"""add pay rates and amounts

Revision ID: b12e45bda29e
Revises: 40a1bbab726b
Create Date: 2026-10-16 10:15:26.533407

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b12e45bda29e"
down_revision: str | Sequence[str] | None = "40a1bbab726b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "core"

# Starting rates for companies that existed before this migration (test data).
START_HOURLY = "450.00"
START_OVERTIME = "675.00"
START_DOUBLE_TIME = "900.00"  # only for companies that have a double-time rule
START_HOLIDAY = "900.00"

TS_TOTAL_HOURS = "regular_hours + overtime_hours + double_time_hours + holiday_hours"
GROSS = "regular_amount + overtime_amount + double_time_amount + holiday_amount"


def _money(name: str, precision: int = 12, **kw: object) -> sa.Column:
    return sa.Column(name, sa.Numeric(precision, 2), **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    # --- companies ------------------------------------------------------------------
    op.add_column(
        "companies",
        sa.Column(
            "aliases",
            sa.ARRAY(sa.String(length=200)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    # Added with a temporary default so existing rows get a value, then the default is
    # dropped: from now on every new company MUST be given its rates.
    for column, start in (
        ("hourly_rate", START_HOURLY),
        ("overtime_rate", START_OVERTIME),
        ("holiday_rate", START_HOLIDAY),
    ):
        op.add_column(
            "companies",
            _money(column, 10, nullable=False, server_default=sa.text(start)),
            schema=SCHEMA,
        )
        op.alter_column("companies", column, server_default=None, schema=SCHEMA)
    op.add_column("companies", _money("double_time_rate", 10, nullable=True), schema=SCHEMA)
    op.execute(
        f"UPDATE {SCHEMA}.companies SET double_time_rate = {START_DOUBLE_TIME} "
        "WHERE double_time_after IS NOT NULL"
    )
    op.add_column(
        "companies",
        sa.Column("currency", sa.CHAR(length=3), server_default="INR", nullable=False),
        schema=SCHEMA,
    )

    op.create_check_constraint(
        op.f("ck_companies_name_not_blank"), "companies", "length(btrim(name)) > 0", schema=SCHEMA
    )
    op.create_check_constraint(
        op.f("ck_companies_rates_positive"),
        "companies",
        "hourly_rate > 0 AND overtime_rate > 0 AND holiday_rate > 0 "
        "AND (double_time_rate IS NULL OR double_time_rate > 0)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_companies_double_time_rate_required"),
        "companies",
        "double_time_after IS NULL OR double_time_rate IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_companies_currency_format"), "companies", "currency ~ '^[A-Z]{3}$'", schema=SCHEMA
    )
    # Name unique ignoring case ("ABC Staffing" = "abc staffing").
    op.execute(f"ALTER TABLE {SCHEMA}.companies DROP CONSTRAINT IF EXISTS uq_companies_name")
    op.create_index(
        "uq_companies_name_lower",
        "companies",
        [sa.text("lower(name)")],
        unique=True,
        schema=SCHEMA,
    )

    # --- timesheets -----------------------------------------------------------------
    op.add_column(
        "timesheets",
        sa.Column(
            "total_hours",
            sa.Numeric(7, 2),
            sa.Computed(TS_TOTAL_HOURS, persisted=True),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column("timesheets", sa.Column("currency", sa.CHAR(length=3)), schema=SCHEMA)
    for column in ("hourly_rate", "overtime_rate", "double_time_rate", "holiday_rate"):
        op.add_column("timesheets", _money(column, 10, nullable=True), schema=SCHEMA)
    for column in ("regular_amount", "overtime_amount", "double_time_amount", "holiday_amount"):
        op.add_column("timesheets", _money(column, 12, nullable=True), schema=SCHEMA)
    op.add_column(
        "timesheets",
        sa.Column(
            "gross_amount", sa.Numeric(12, 2), sa.Computed(GROSS, persisted=True), nullable=True
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_amounts_non_negative"),
        "timesheets",
        "(regular_amount IS NULL OR regular_amount >= 0) "
        "AND (overtime_amount IS NULL OR overtime_amount >= 0) "
        "AND (double_time_amount IS NULL OR double_time_amount >= 0) "
        "AND (holiday_amount IS NULL OR holiday_amount >= 0)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_timesheets_currency_format"),
        "timesheets",
        "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
        schema=SCHEMA,
    )

    # Price the existing timesheets with their company's rates (same rule as the code:
    # no hours -> 0.00; hours but no rate -> NULL, which a recalculate will flag).
    op.execute(
        f"""
        UPDATE {SCHEMA}.timesheets t
        SET currency = c.currency,
            hourly_rate = c.hourly_rate,
            overtime_rate = c.overtime_rate,
            double_time_rate = c.double_time_rate,
            holiday_rate = c.holiday_rate,
            regular_amount = round(t.regular_hours * c.hourly_rate, 2),
            overtime_amount = round(t.overtime_hours * c.overtime_rate, 2),
            double_time_amount = CASE
                WHEN t.double_time_hours = 0 THEN 0
                ELSE round(t.double_time_hours * c.double_time_rate, 2) END,
            holiday_amount = round(t.holiday_hours * c.holiday_rate, 2)
        FROM {SCHEMA}.companies c
        WHERE t.company_id = c.id
        """
    )

    # --- export_batches -------------------------------------------------------------
    op.add_column(
        "export_batches",
        sa.Column("currency", sa.CHAR(length=3), server_default="INR", nullable=False),
        schema=SCHEMA,
    )
    for column in ("regular_amount", "overtime_amount", "double_time_amount", "holiday_amount"):
        op.add_column(
            "export_batches",
            _money(column, 14, nullable=False, server_default=sa.text("0")),
            schema=SCHEMA,
        )
    op.add_column(
        "export_batches",
        sa.Column(
            "gross_amount", sa.Numeric(14, 2), sa.Computed(GROSS, persisted=True), nullable=True
        ),
        schema=SCHEMA,
    )
    # Earlier exports: totals from the timesheets they contain (the CSV file itself is
    # kept as it was produced).
    op.execute(
        f"""
        UPDATE {SCHEMA}.export_batches b
        SET currency = c.currency,
            regular_amount = s.regular_amount,
            overtime_amount = s.overtime_amount,
            double_time_amount = s.double_time_amount,
            holiday_amount = s.holiday_amount
        FROM {SCHEMA}.companies c,
             (SELECT export_batch_id,
                     coalesce(sum(regular_amount), 0) AS regular_amount,
                     coalesce(sum(overtime_amount), 0) AS overtime_amount,
                     coalesce(sum(double_time_amount), 0) AS double_time_amount,
                     coalesce(sum(holiday_amount), 0) AS holiday_amount
              FROM {SCHEMA}.timesheets
              WHERE export_batch_id IS NOT NULL
              GROUP BY export_batch_id) s
        WHERE b.company_id = c.id AND s.export_batch_id = b.id
        """
    )


def downgrade() -> None:
    for column in (
        "gross_amount",
        "holiday_amount",
        "double_time_amount",
        "overtime_amount",
        "regular_amount",
        "currency",
    ):
        op.drop_column("export_batches", column, schema=SCHEMA)

    op.drop_constraint(op.f("ck_timesheets_currency_format"), "timesheets", schema=SCHEMA)
    op.drop_constraint(op.f("ck_timesheets_amounts_non_negative"), "timesheets", schema=SCHEMA)
    for column in (
        "gross_amount",
        "holiday_amount",
        "double_time_amount",
        "overtime_amount",
        "regular_amount",
        "holiday_rate",
        "double_time_rate",
        "overtime_rate",
        "hourly_rate",
        "currency",
        "total_hours",
    ):
        op.drop_column("timesheets", column, schema=SCHEMA)

    op.drop_index("uq_companies_name_lower", table_name="companies", schema=SCHEMA)
    op.create_unique_constraint(op.f("uq_companies_name"), "companies", ["name"], schema=SCHEMA)
    for name in (
        "ck_companies_currency_format",
        "ck_companies_double_time_rate_required",
        "ck_companies_rates_positive",
        "ck_companies_name_not_blank",
    ):
        op.drop_constraint(op.f(name), "companies", schema=SCHEMA)
    for column in (
        "currency",
        "double_time_rate",
        "holiday_rate",
        "overtime_rate",
        "hourly_rate",
        "aliases",
    ):
        op.drop_column("companies", column, schema=SCHEMA)
