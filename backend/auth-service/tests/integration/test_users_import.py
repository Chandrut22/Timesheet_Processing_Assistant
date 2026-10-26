"""Bulk import of users through the HTTP API, on a real database (see conftest.py)."""

import io
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openpyxl
import pytest
from sqlalchemy import select, text

from src.api.rest.routes import users as users_routes
from src.config.settings import settings
from src.core.security import create_access_token, hash_password, verify_password
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Role, User

HEADER = "name,email,role,password"


def csv_file(*lines: str, name: str = "users.csv") -> dict[str, Any]:
    return {"file": (name, ("\r\n".join(lines) + "\r\n").encode(), "text/csv")}


def xlsx_file(rows: list[list[Any]], name: str = "users.xlsx") -> dict[str, Any]:
    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return {"file": (name, out.getvalue(), "application/octet-stream")}


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


async def emails_in_db() -> set[str]:
    async with SessionLocal() as s:
        return set((await s.scalars(select(User.email))).all())


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Welcome emails the routes queued (instead of sending them)."""
    calls: list[dict[str, str]] = []

    async def fake_send(**kwargs: str) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(users_routes, "send_welcome_email", fake_send)
    return calls


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


async def test_template_has_the_exact_headers(client: httpx.AsyncClient) -> None:
    r = await client.get("/users/import/template")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "users-import-template.csv" in r.headers["content-disposition"]
    assert r.text.lstrip("﻿").splitlines()[0] == HEADER


async def test_dry_run_writes_nothing_and_emails_nobody(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = csv_file(HEADER, "Ben,ben@example.com,reviewer,Secret-pass-1")
    r = await client.post("/users/import", files=files)  # dry_run defaults to true
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["dry_run"], body["committed"], body["created"]) == (True, False, 1)
    assert "Secret-pass-1" not in r.text
    assert await emails_in_db() == {"ada@example.com"}
    assert sent == []


async def test_commit_creates_users_and_sends_their_passwords(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = csv_file(
        HEADER,
        "Ben Rao,Ben@Example.com,Reviewer,Secret-pass-1",
        "Cara,cara@example.com,admin,",
    )
    r = await client.post("/users/import?dry_run=false", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["committed"], body["created"], body["failed"]) == (True, 2, 0)
    assert "Secret-pass-1" not in r.text
    assert await emails_in_db() == {
        "ada@example.com",
        "ben@example.com",
        "cara@example.com",
    }

    by_email = {c["to"]: c for c in sent}
    assert set(by_email) == {"ben@example.com", "cara@example.com"}
    assert by_email["ben@example.com"]["password"] == "Secret-pass-1"
    assert by_email["ben@example.com"]["role"] == "reviewer"
    generated = by_email["cara@example.com"]["password"]
    assert len(generated) >= 16
    async with SessionLocal() as s:
        cara = await s.scalar(select(User).where(User.email == "cara@example.com"))
        assert cara is not None and cara.role.name == "admin"
        assert verify_password(generated, cara.password_hash)


async def test_bad_rows_are_reported_per_column_without_the_password(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = csv_file(
        HEADER,
        "Ben,not-an-email,reviewer,",
        "Cara,cara@example.com,boss,",
        "Dev,dev@example.com,reviewer,short7!",
        ",eve@example.com,reviewer,",
        "Fay,fay@example.com,reviewer,",
    )
    r = await client.post("/users/import?dry_run=false&on_error=skip", files=files)
    body = r.json()
    assert (body["committed"], body["created"], body["failed"]) == (True, 1, 4)
    errors = {row["row"]: row["errors"][0]["column"] for row in body["rows"][:4]}
    assert errors == {2: "email", 3: "role", 4: "password", 5: "name"}
    assert "short7!" not in r.text
    assert await emails_in_db() == {"ada@example.com", "fay@example.com"}
    assert [c["to"] for c in sent] == ["fay@example.com"]


async def test_abort_writes_nothing_when_a_row_fails(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = csv_file(HEADER, "Ben,ben@example.com,reviewer,", "Cara,bad,reviewer,")
    r = await client.post("/users/import?dry_run=false", files=files)
    body = r.json()
    assert (body["committed"], body["created"], body["failed"]) == (False, 1, 1)
    assert await emails_in_db() == {"ada@example.com"}
    assert sent == []


async def test_existing_and_repeated_emails(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = csv_file(
        HEADER,
        "Ada Again,ADA@example.com,reviewer,",
        "Ben,ben@example.com,reviewer,",
        "Ben Twice,ben@example.com,admin,",
    )
    r = await client.post("/users/import?on_error=skip", files=files)
    rows = {row["row"]: row for row in r.json()["rows"]}
    assert rows[2]["status"] == "failed" and "Already exists" in str(rows[2]["errors"])
    assert rows[4]["status"] == "failed" and "row 3" in str(rows[4]["errors"])

    r = await client.post("/users/import?on_duplicate=skip&on_error=skip", files=files)
    assert r.json()["skipped"] == 1


async def test_update_is_not_allowed_for_users(client: httpx.AsyncClient) -> None:
    files = csv_file(HEADER, "Ada,ada@example.com,reviewer,")
    r = await client.post("/users/import?on_duplicate=update", files=files)
    assert r.status_code == 422
    assert "not allowed" in r.json()["detail"]


async def test_xlsx_files_work(
    client: httpx.AsyncClient, sent: list[dict[str, str]]
) -> None:
    files = xlsx_file(
        [["Name", "Email", "Role", "Password"], ["Gil", "gil@example.com", "reviewer"]]
    )
    r = await client.post("/users/import?dry_run=false", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    assert "gil@example.com" in await emails_in_db()


async def test_unsafe_or_wrong_files_are_refused(client: httpx.AsyncClient) -> None:
    fake = {"file": ("users.xlsx", b"name,email\r\n", "application/octet-stream")}
    r = await client.post("/users/import", files=fake)
    assert r.status_code == 422 and "not a real" in r.json()["detail"]

    r = await client.post("/users/import", files=csv_file("name,email", "a,b"))
    assert r.status_code == 422 and "role" in r.json()["detail"]

    txt = {"file": ("users.txt", b"x", "text/plain")}
    assert (await client.post("/users/import", files=txt)).status_code == 422


async def test_row_cap(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_user_import_rows", 2)
    lines = [f"U{i},u{i}@example.com,reviewer," for i in range(3)]
    r = await client.post("/users/import", files=csv_file(HEADER, *lines))
    assert r.status_code == 422 and "limit is 2" in r.json()["detail"]


async def test_only_admins(admin: User) -> None:
    from src.main import app

    reviewer = await add_user("rev@example.com", "reviewer")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        files = csv_file(HEADER)
        assert (await c.post("/users/import", files=files)).status_code == 401
        r = await c.post(
            "/users/import", files=files, headers=bearer(reviewer, "reviewer")
        )
        assert r.status_code == 403
        r = await c.get("/users/import/template", headers=bearer(reviewer, "reviewer"))
        assert r.status_code == 403


async def test_committed_import_is_logged_without_passwords(
    client: httpx.AsyncClient,
    admin: User,
    sent: list[dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="src.core.services.importing.service")
    files = csv_file(HEADER, "Hal,hal@example.com,reviewer,Secret-pass-9")
    await client.post("/users/import?dry_run=false", files=files)
    lines = [
        r.getMessage() for r in caplog.records if "Users imported" in r.getMessage()
    ]
    assert len(lines) == 1
    assert str(admin.id) in lines[0] and "created=1" in lines[0]
    assert "Secret-pass-9" not in caplog.text
