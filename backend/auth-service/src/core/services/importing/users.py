import asyncio
import secrets
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.core.services.importing.runner import Column, Resource
from src.core.services.user_service import UserService
from src.data.repositories.user_repository import UserRepository
from src.schemas.user import UserCreate

USER_COLUMNS = (
    Column("name", True, "Anita Desai"),
    Column("email", True, "anita.desai@example.com", "Must be new: one account each"),
    Column("role", True, "reviewer", "admin or reviewer"),
    Column(
        "password",
        False,
        "",
        "Blank = a random password; it is sent in the welcome email either way",
    ),
)


def random_password() -> str:
    return secrets.token_urlsafe(12)  # 16 characters, ~96 bits


@dataclass(slots=True)
class Welcome:
    """Who gets a welcome email once the import is committed."""

    email: str
    name: str
    role: str
    password: str = field(repr=False)  # never shown in logs or tracebacks


# Stands in for the hash during a dry run (everything is rolled back): Argon2 is slow
# on purpose, and checking a file should not cost seconds per row.
DRY_RUN_HASH = "!dry-run"


def users(session: AsyncSession, welcomes: list[Welcome], *, dry_run: bool) -> Resource:
    service = UserService(session)
    repo = UserRepository(session)

    async def parse(row: dict[str, str]) -> tuple[Any, Hashable]:
        password = row.get("password", "") or random_password()
        data = UserCreate(
            name=row.get("name", ""),
            email=row.get("email", ""),
            role=row.get("role", "").strip().lower(),  # type: ignore[arg-type]
            password=password,
        )
        return data, data.email.strip().lower()

    async def find(key: Hashable) -> Any:
        return await repo.get_by_email(str(key))

    async def create(data: Any) -> Any:
        assert isinstance(data, UserCreate)
        if dry_run:
            password_hash = DRY_RUN_HASH
        else:  # in a worker thread, so other requests are served meanwhile
            password_hash = await asyncio.to_thread(hash_password, data.password)
        # add_new flushes: a refused INSERT raises here, before the email is queued.
        user = await service.add_new(data, password_hash=password_hash)
        welcomes.append(Welcome(user.email, user.name, data.role.value, data.password))
        return user

    return Resource(
        name="users",
        columns=USER_COLUMNS,
        natural_key="email",
        parse=parse,
        find=find,
        create=create,
        update=None,
    )
