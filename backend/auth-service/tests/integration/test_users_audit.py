"""users.created_at / updated_at / created_by / updated_by: the admin who creates or
changes a user, the user themself when they sign in, and NULL (the system) outside a
request. Real database, see conftest.py."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select, text

from src.core.security import create_access_token, hash_password
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Role, User


async def add_user(email: str, role: str) -> User:
    async with SessionLocal() as s:
        role_row = await s.scalar(select(Role).where(Role.name == role))
        assert role_row is not None
        user = User(
            name=email.split("@")[0],
            email=email,
            password_hash=hash_password("Existing-pass-1"),
            role_id=role_row.id,
        )
        s.add(user)
        await s.commit()
        return user


def bearer(user: User, role: str) -> dict[str, str]:
    token = create_access_token(user.id, role, user.name, user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin() -> AsyncIterator[User]:
    async with SessionLocal() as s:
        await s.execute(text("TRUNCATE auth.users CASCADE"))
        await s.commit()
    yield await add_user("ada@example.com", "admin")
    await engine.dispose()


@pytest.fixture
async def client(admin: User) -> AsyncIterator[httpx.AsyncClient]:
    from src.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
        headers=bearer(admin, "admin"),
    ) as c:
        yield c


async def stored(email: str) -> User:
    async with SessionLocal() as s:
        user = await s.scalar(select(User).where(User.email == email))
        assert user is not None
        return user


async def test_the_admin_is_recorded_on_create_and_change(
    client: httpx.AsyncClient, admin: User
) -> None:
    assert admin.created_by is None  # made outside a request (like the seed script)

    created = await client.post(
        "/users",
        json={
            "name": "Rita Reviewer",
            "email": "rita@example.com",
            "password": "Strong-pass-123",
            "role": "reviewer",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created_by"] == body["updated_by"] == str(admin.id)
    assert body["created_at"] and body["updated_at"]

    other_admin = await add_user("ravi@example.com", "admin")
    changed = await client.patch(
        f"/users/{body['id']}",
        json={"name": "Rita R."},
        headers=bearer(other_admin, "admin"),
    )
    assert changed.status_code == 200, changed.text
    after = changed.json()
    assert after["created_by"] == str(admin.id)
    assert after["updated_by"] == str(other_admin.id)
    assert after["updated_at"] > body["updated_at"]


async def test_signing_in_is_recorded_as_the_user_themself(
    client: httpx.AsyncClient, admin: User
) -> None:
    rita = await add_user("rita@example.com", "reviewer")
    signed_in = await client.post(
        "/auth/login", json={"email": "rita@example.com", "password": "Existing-pass-1"}
    )
    assert signed_in.status_code == 200, signed_in.text
    row = await stored("rita@example.com")
    assert row.last_login_at is not None
    assert row.updated_by == rita.id
