from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Every auth-service table lives in this Postgres schema (auth.users, auth.roles).
# The database is shared with core-service, which uses its own "core" schema.
SCHEMA = "auth"

# Gives every constraint and index a predictable name (pk_users, uq_users_email,
# fk_users_role_id_roles, ...). Without it Postgres picks names for you, and
# later migrations that drop or change a constraint become guesswork.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    # schema=SCHEMA: every table, query and insert is written as auth.<table>.
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)