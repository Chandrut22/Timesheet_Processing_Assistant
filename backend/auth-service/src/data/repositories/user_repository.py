"""All database queries for users live here, so services stay free of SQL."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.roles import RoleName
from src.data.models import Role, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.email == email.strip().lower())
        )

    async def get_role(self, name: str) -> Role | None:
        return await self.session.scalar(select(Role).where(Role.name == name))

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()  # sends the INSERT now (catches errors early)
        return user

    async def search(
        self,
        *,
        role: str | None,
        is_active: bool | None,
        q: str | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[User], int]:
        """One page of users plus the total count, newest first."""
        query = select(User).join(User.role)
        if role:
            query = query.where(Role.name == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if q:
            pattern = f"%{q.strip()}%"
            query = query.where(
                or_(User.name.ilike(pattern), User.email.ilike(pattern))
            )

        total = await self.session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        rows = await self.session.scalars(
            # UUIDs are random, so they no longer sort by age; created_at does that.
            # id is only a tie-breaker that keeps paging stable.
            query.order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return rows.all(), total or 0

    async def count_active_super_admins(self) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .join(User.role)
            .where(Role.name == RoleName.SUPER_ADMIN, User.is_active.is_(True))
        )
        return count or 0
