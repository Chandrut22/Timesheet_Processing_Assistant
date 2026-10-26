"""GET /submissions: an email carries mail_url ("Open in Gmail"), an upload does not, and
the Message-ID itself is never sent. Real database, see conftest.py."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from src.config.settings import settings
from src.core.rbac import tokens
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Submission

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)
BOX = "timesheets@genworx.example"


def bearer() -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": "reviewer",
        "name": "Ravi Reviewer",
        "email": "ravi@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, KEY, algorithm='RS256')}"}


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    monkeypatch.setattr(settings, "mailbox_account", BOX)
    async with SessionLocal() as s:
        await s.execute(text("TRUNCATE core.submissions CASCADE"))
        await s.commit()
    from src.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def add(**fields: object) -> uuid.UUID:
    async with SessionLocal() as s:
        submission = Submission(received_at=datetime.now(UTC), **fields)
        s.add(submission)
        await s.commit()
        return submission.id


async def test_email_has_a_gmail_link_and_upload_has_none(client: httpx.AsyncClient) -> None:
    email = await add(
        source="email",
        sender_email="payroll@lakeside.example",
        subject="Week 42",
        message_id="<week42@lakeside.example>",
    )
    upload = await add(source="upload", uploaded_by_name="Ravi Reviewer")

    one = await client.get(f"/submissions/{email}", headers=bearer())
    assert one.status_code == 200, one.text
    assert one.json()["mail_url"] == (
        f"https://mail.google.com/mail/?authuser={BOX}"
        "#search/rfc822msgid%3Aweek42%40lakeside.example"
    )
    assert "message_id" not in one.json()

    listed = await client.get("/submissions", headers=bearer())
    assert listed.status_code == 200, listed.text
    urls = {item["id"]: item["mail_url"] for item in listed.json()["items"]}
    assert urls[str(email)] == one.json()["mail_url"]
    assert urls[str(upload)] is None
