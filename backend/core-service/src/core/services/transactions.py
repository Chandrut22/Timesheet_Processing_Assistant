"""Transaction helpers for the services (a database refusal becomes an app error)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError


async def commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit; a unique-constraint race (two admins at once) becomes a clean 409."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc
