"""User management rules. Routes check *who* may call (admins only); this checks
*what* is allowed."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.roles import RoleName
from src.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ValidationFailedError,
)
from src.core.security import hash_password, verify_password
from src.data.models import User
from src.data.repositories.user_repository import UserRepository
from src.schemas.user import BulkUserItem, BulkUserResult, UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def list(
        self,
        *,
        role: str | None,
        is_active: bool | None,
        q: str | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[User], int]:
        return await self.users.search(
            role=role, is_active=is_active, q=q, page=page, size=size
        )

    async def create(self, data: UserCreate) -> User:
        """Only admins get here (route guard); they may create admins or reviewers."""
        user = await self.add_new(data)
        await self.session.commit()
        await self.session.refresh(user, ["role"])
        return user

    async def add_new(
        self, data: UserCreate, *, password_hash: str | None = None
    ) -> User:
        """The rules for a new user, without committing (the bulk import commits once
        for the whole file, and passes a hash it made off the event loop)."""
        email = data.email.strip().lower()
        if await self.users.get_by_email(email) is not None:
            raise ConflictError("A user with this email already exists.")
        role = await self.users.get_role(data.role)
        if role is None:
            raise ValidationFailedError(f"Unknown role '{data.role}'.")

        user = await self.users.add(
            User(
                name=data.name,
                email=email,
                password_hash=password_hash or hash_password(data.password),
                role_id=role.id,
            )
        )
        return user

    async def update(self, user_id: uuid.UUID, data: UserUpdate, actor: User) -> User:
        user = await self.get(user_id)
        changes = data.model_dump(exclude_unset=True)  # only fields that were sent

        if changes.get("name") is not None:
            user.name = changes["name"].strip()

        new_role = changes.get("role")
        if new_role is not None and new_role != user.role.name:
            if user.id == actor.id:
                raise ConflictError("You cannot change your own role.")
            await self._keep_one_admin(user)
            role = await self.users.get_role(new_role)
            if role is None:
                raise ValidationFailedError(f"Unknown role '{new_role}'.")
            user.role_id = role.id

        if changes.get("is_active") is False and user.is_active:
            if user.id == actor.id:
                raise ConflictError("You cannot deactivate your own account.")
            await self._keep_one_admin(user)
            user.is_active = False
        elif changes.get("is_active") is True:
            user.is_active = True

        await self.session.commit()
        await self.session.refresh(user, ["role"])
        return user

    async def bulk_status(
        self, ids: Sequence[uuid.UUID], is_active: bool, actor: User
    ) -> BulkUserResult:
        """Activate / deactivate many users with the same rules as one (never yourself,
        never the last active admin: checked user by user, so a batch with every admin
        stops at the last one). Each user is committed on its own."""
        results: list[BulkUserItem] = []
        for user_id in ids:
            try:
                user = await self.get(user_id)
                changed = user.is_active != is_active
                if changed:
                    await self.update(user_id, UserUpdate(is_active=is_active), actor)
                results.append(
                    BulkUserItem(
                        id=user_id, ok=True, changed=changed, is_active=is_active
                    )
                )
            except AppError as exc:
                # The rules are checked before anything changes, so there is nothing to
                # roll back (a rollback would also expire the signed-in admin's row).
                results.append(BulkUserItem(id=user_id, ok=False, error=exc.message))
        succeeded = sum(1 for r in results if r.ok)
        return BulkUserResult(
            requested=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
        )

    async def reset_password(self, user_id: uuid.UUID, new_password: str) -> None:
        user = await self.get(user_id)
        user.password_hash = hash_password(new_password)
        await self.session.commit()

    async def change_own_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise ValidationFailedError("Current password is incorrect.")
        if current == new:
            raise ValidationFailedError("The new password must be different.")
        user.password_hash = hash_password(new)
        await self.session.commit()

    async def _keep_one_admin(self, user: User) -> None:
        """Refuse to demote or deactivate the only active admin (nobody could manage
        users any more)."""
        if (
            user.is_active
            and user.role.name == RoleName.ADMIN
            and await self.users.count_active_admins() <= 1
        ):
            raise ConflictError(
                "The last active admin cannot be demoted or deactivated."
            )
