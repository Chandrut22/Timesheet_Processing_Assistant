"""Fuzzy employee names with pg_trgm: employees.name_keys (no extra table)

- extensions pg_trgm (trigram similarity + GIN index) and unaccent (José -> jose), both
  "trusted" since PostgreSQL 13, so the database owner can enable them
- core.name_key(text): one name cleaned for comparing (lowercase, no accents,
  punctuation -> spaces)
- core.employee_name_keys(full_name, aliases): every name of an employee, cleaned, in one
  text ("john smith bob"). Both are IMMUTABLE (they wrap unaccent / array_to_string,
  which are only STABLE in general but always give the same answer here), so they can be
  used by a generated column and an index.
- employees.name_keys: GENERATED ALWAYS AS (core.employee_name_keys(...)) STORED, so
  Postgres keeps it up to date on every insert / update (no trigger), with a GIN trigram
  index. Searched with word_similarity / <%, which scores the best-matching part of the
  text, so an alias next to the full name still scores fully.
- Adding a stored generated column rewrites the employees table once (quick: a few
  thousand rows at most).

Also removes what an earlier draft of this change created (core.employee_names, its
trigger and function) if a database has them; see the notes for databases that ran it.

Revision ID: c4d8a2e6f0b3
Revises: a7c3e9f5b1d8
Create Date: 2026-10-27 14:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8a2e6f0b3"
down_revision: str | Sequence[str] | None = "a7c3e9f5b1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
INDEX = "ix_employees_name_keys_trgm"

NAME_KEY = f"""
CREATE OR REPLACE FUNCTION {SCHEMA}.name_key(raw text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT btrim(regexp_replace(
           regexp_replace(lower(public.unaccent('public.unaccent'::regdictionary, raw)),
                          '[^a-z0-9 ]+', ' ', 'g'),
           ' +', ' ', 'g'))
$$
"""

NAME_KEYS = f"""
CREATE OR REPLACE FUNCTION {SCHEMA}.employee_name_keys(full_name text, aliases text[])
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT btrim(coalesce({SCHEMA}.name_key(full_name), '') || ' ' ||
               coalesce({SCHEMA}.name_key(array_to_string(aliases, ' ')), ''))
$$
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public")
    # Leftovers of the earlier draft (employee_names table), if this database has them.
    op.execute(f"DROP TRIGGER IF EXISTS trg_employees_sync_names ON {SCHEMA}.employees")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.sync_employee_names()")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.employee_names")

    op.execute(NAME_KEY)
    op.execute(NAME_KEYS)
    op.execute(
        f"ALTER TABLE {SCHEMA}.employees ADD COLUMN name_keys text "
        f"GENERATED ALWAYS AS ({SCHEMA}.employee_name_keys(full_name, aliases::text[])) STORED"
    )
    op.execute(
        f"CREATE INDEX {INDEX} ON {SCHEMA}.employees USING gin (name_keys public.gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.{INDEX}")
    op.execute(f"ALTER TABLE {SCHEMA}.employees DROP COLUMN IF EXISTS name_keys")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.employee_name_keys(text, text[])")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.name_key(text)")
