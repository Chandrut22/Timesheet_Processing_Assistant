"""Activating / deactivating many users at once, through the HTTP API, on a real
database (see conftest.py)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select, text

from src.core.security import create_access_token, hash_password
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Role, User


async def add_user(email: str, role: str, *, active: bool = True) -> User:
    async with SessionLocal() as s:
        role_row = await s.scalar(select(Role).where(Role.name == role))
        assert role_row is not None
        user = User(
            name=email.split("@")[0],
            email=email,
            password_hash=hash_password("Existing-pass-1"),
            role_id=role_row.id,
            is_active=active,
        )
        s.add(user)
        await s.commit()
        return user


def bearer(user: User, role: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, role, user.name, user.email)}"
    }


async def active(user_id: uuid.UUID) -> bool:
    async with SessionLocal() as s:
        user = await s.get(User, user_id)
        assert user is not None
        return user.is_active


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


async def test_deactivate_and_activate_several_users(
    client: httpx.AsyncClient, admin: User
) -> None:
    rita = await add_user("rita@example.com", "reviewer")
    ravi = await add_user("ravi@example.com", "reviewer", active=False)
    ids = [str(rita.id), str(ravi.id)]

    off = (
        await client.post("/users/bulk/status", json={"ids": ids, "is_active": False})
    ).json()
    assert (off["requested"], off["succeeded"], off["failed"]) == (2, 2, 0)
    assert [(r["changed"], r["is_active"]) for r in off["results"]] == [
        (True, False),
        (False, False),
    ]
    assert not await active(rita.id)

    on = (
        await client.post("/users/bulk/status", json={"ids": ids, "is_active": True})
    ).json()
    assert on["succeeded"] == 2 and await active(rita.id) and await active(ravi.id)


async def test_never_yourself_and_never_the_last_admin(
    client: httpx.AsyncClient, admin: User
) -> None:
    grace = await add_user("grace@example.com", "admin")
    rita = await add_user("rita@example.com", "reviewer")
    unknown = uuid.uuid4()
    body = {
        "ids": [str(admin.id), str(grace.id), str(rita.id), str(unknown)],
        "is_active": False,
    }
    result = (await client.post("/users/bulk/status", json=body)).json()

    by_id = {r["id"]: r for r in result["results"]}
    assert (
        not by_id[str(admin.id)]["ok"] and "your own" in by_id[str(admin.id)]["error"]
    )
    assert by_id[str(grace.id)]["ok"] and by_id[str(rita.id)]["ok"]
    assert not by_id[str(unknown)]["ok"]
    assert (result["succeeded"], result["failed"]) == (2, 2)
    assert await active(admin.id)  # still an active admin left: you

    assert not await active(grace.id) and not await active(rita.id)


async def test_the_last_admin_stays_even_in_a_batch(admin: User) -> None:
    from src.main import app

    grace = await add_user("grace@example.com", "admin")
    # Grace deactivates every admin: Ada goes, Grace (herself) is refused, so one stays.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://t",
        headers=bearer(grace, "admin"),
    ) as c:
        body = {"ids": [str(admin.id), str(grace.id)], "is_active": False}
        result = (await c.post("/users/bulk/status", json=body)).json()
    assert [r["ok"] for r in result["results"]] == [True, False]
    assert not await active(admin.id) and await active(grace.id)


async def test_admins_only_and_valid_requests(
    client: httpx.AsyncClient, admin: User
) -> None:
    rita = await add_user("rita@example.com", "reviewer")
    body = {"ids": [str(rita.id)], "is_active": False}
    assert (
        await client.post(
            "/users/bulk/status", json=body, headers=bearer(rita, "reviewer")
        )
    ).status_code == 403
    assert (
        await client.post(
            "/users/bulk/status", json=body, headers={"Authorization": ""}
        )
    ).status_code == 401
    twice = {"ids": [str(rita.id), str(rita.id)], "is_active": False}
    assert (await client.post("/users/bulk/status", json=twice)).status_code == 422
    too_many = {"ids": [str(uuid.uuid4()) for _ in range(101)], "is_active": False}
    assert (await client.post("/users/bulk/status", json=too_many)).status_code == 422
