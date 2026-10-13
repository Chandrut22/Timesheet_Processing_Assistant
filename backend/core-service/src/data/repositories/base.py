from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError
from src.data.models import Base


class BaseRepository[ModelT: Base]:
    """get / add / delete / paginate, shared by every repository."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: Any) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()  # INSERT now, so constraint errors surface early
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def paginate(
        self, query: Select[Any], *, page: int, size: int
    ) -> tuple[Sequence[ModelT], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        rows = await self.session.scalars(query.offset((page - 1) * size).limit(size))
        return rows.all(), total or 0


async def commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit; a unique-constraint race (two admins at once) becomes a clean 409."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc
