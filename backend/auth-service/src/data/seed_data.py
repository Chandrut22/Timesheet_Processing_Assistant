"""Startup seed: the rows the app cannot work without.

Runs every time the server starts (see lifespan in main.py). Safe to repeat:
existing rows are left alone, and two servers starting together cannot
create duplicates (the database's unique constraints decide).

    - the two roles (admin, reviewer)
    - the first admin, from BOOTSTRAP_ADMIN_* (only if no admin exists)
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.security import hash_password
from src.data.clients.postgres import SessionLocal
from src.data.models import Role, User

logger = logging.getLogger(__name__)


async def seed_roles(session: AsyncSession) -> int:
    """Insert missing roles. Returns how many were added."""
    stmt = (
        insert(Role)
        .values([{"name": role.value} for role in RoleName])  # id: gen_random_uuid()
        # Already there? Skip it. This is what makes the seed safe to repeat.
        .on_conflict_do_nothing(index_elements=[Role.name])
        .returning(Role.id)
    )
    added = len((await session.execute(stmt)).all())
    await session.commit()
    return added


async def seed_admin(session: AsyncSession) -> bool:
    """Create the first super admin from settings when none exists yet.
    Returns True if one was created."""
    email = settings.bootstrap_admin_email
    password = settings.bootstrap_admin_password
    if not email or password is None:
        return False  # not configured: nothing to do

    role = await session.scalar(select(Role).where(Role.name == RoleName.ADMIN))
    if role is None:
        return False

    existing = await session.scalar(
        select(func.count()).select_from(User).where(User.role_id == role.id)
    )
    if existing:
        return False  # a super admin already exists; never touch it

    if len(password.get_secret_value()) < 8:
        logger.warning(
            "BOOTSTRAP_ADMIN_PASSWORD is shorter than 8 characters; skipped."
        )
        return False

    session.add(
        User(
            name=settings.bootstrap_admin_name,
            email=email.strip().lower(),
            password_hash=hash_password(password.get_secret_value()),
            role_id=role.id,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # Another server process created it at the same moment, or the email
        # already belongs to a non-admin user. Either way: leave it.
        await session.rollback()
        return False
    return True


async def run_seed() -> None:
    """Called once at startup."""
    try:
        async with SessionLocal() as session:
            added = await seed_roles(session)
            if added:
                logger.info("Seed: added %d role(s)", added)
            if await seed_admin(session):
                logger.info(
                    "Seed: created super admin %s", settings.bootstrap_admin_email
                )
    except ProgrammingError as exc:
        # Most likely the tables do not exist yet.
        raise RuntimeError(
            "Seeding failed: the tables are missing. Run `alembic upgrade head` first."
        ) from exc
