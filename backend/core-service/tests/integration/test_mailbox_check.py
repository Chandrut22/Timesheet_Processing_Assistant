""" "Check mail now": the API (status, request, cooldown, result, audit) and the listener's
side (manual check on a second connection, requests while reconnecting, the lock).
Real PostgreSQL and Redis (see conftest.py); the mailbox is a fake."""

import asyncio
import json
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage, Message
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from src.config.settings import settings
from src.control.workers import email_listener as el
from src.core.rbac import tokens
from src.data.clients.mailbox_signals import (
    CHECK_CHANNEL,
    COOLDOWN_KEY,
    LOCK_KEY,
    STATUS_KEY,
    CatchUpLock,
    read_result,
    update_result,
)
from src.data.clients.postgres import SessionLocal, engine
from src.data.clients.redis import redis_client
from src.data.models import AuditEvent
from src.handlers.email.listener import CURSOR_KEY, Cursor

# Deletes the listener's Redis keys: only against TEST_REDIS_URL (conftest.py).
pytestmark = pytest.mark.redis

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    KEY.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


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


@pytest.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    await redis_client.delete(STATUS_KEY, COOLDOWN_KEY, LOCK_KEY, CURSOR_KEY)
    yield
    await redis_client.delete(STATUS_KEY, COOLDOWN_KEY, LOCK_KEY, CURSOR_KEY)
    await redis_client.connection_pool.disconnect()


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(tokens, "public_key", lambda: PUBLIC)
    from src.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def heartbeat(age_s: float = 5, **fields: str) -> None:
    # Any: the mapping's type differs between redis versions (5/6 vs 7/8 stubs)
    mapping: dict[Any, Any] = {
        "alive_at": str(time.time() - age_s),
        "enabled": "1",
        "connected": "1",
        **fields,
    }
    await redis_client.hset(STATUS_KEY, mapping=mapping)


# ------------------------------------------------------------------ API


async def test_not_running_turned_off_and_status(client: httpx.AsyncClient) -> None:
    down = await client.post("/email/check-now", headers=bearer())
    assert down.status_code == 503 and down.json()["code"] == "email_listener_down"

    await redis_client.hset(STATUS_KEY, mapping={"enabled": "0", "alive_at": str(time.time())})
    off = await client.post("/email/check-now", headers=bearer())
    assert off.status_code == 409

    await heartbeat(mailbox="inbox@x.example", last_found="2")
    status = (await client.get("/email/status", headers=bearer())).json()
    assert status["running"] and status["connected"] and status["mailbox"] == "inbox@x.example"
    assert status["last_found"] == 2 and status["cooldown_seconds"] == 0


async def test_request_cooldown_result_and_audit(client: httpx.AsyncClient) -> None:
    await heartbeat()
    pubsub = redis_client.pubsub()  # stands in for the listener
    await pubsub.subscribe(CHECK_CHANNEL)
    try:
        first = await client.post("/email/check-now", headers=bearer())
        assert first.status_code == 202, first.text
        body = first.json()
        assert body["state"] == "queued" and body["requested_by"] == "Ravi Reviewer"
        request_id = body["request_id"]

        message = None
        for _ in range(20):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if message:
                break
        assert message and json.loads(message["data"]) == {"request_id": request_id}

        again = await client.post("/email/check-now", headers=bearer())
        assert again.status_code == 429 and again.json()["code"] == "check_cooldown"
        assert (
            1 <= int(again.headers["Retry-After"]) <= settings.email_manual_check_cooldown_seconds
        )

        await update_result(redis_client, request_id, state="done", found=3, queued=2, ignored=1)
        done = (await client.get(f"/email/check-now/{request_id}", headers=bearer())).json()
        assert done["state"] == "done" and (done["found"], done["queued"]) == (3, 2)
        assert (await client.get("/email/check-now/nope", headers=bearer())).status_code == 404

        async with SessionLocal() as s:
            event = await s.scalar(
                select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(request_id))
            )
        assert event is not None and event.action == "email_check_requested"
        assert event.entity_type == "mailbox" and event.actor_name == "Ravi Reviewer"
    finally:
        await cast(Any, pubsub).aclose()  # untyped in some redis versions


async def test_no_subscriber_means_down_and_frees_the_cooldown(client: httpx.AsyncClient) -> None:
    await heartbeat()  # a heartbeat, but nobody listening on the channel
    r = await client.post("/email/check-now", headers=bearer())
    assert r.status_code == 503
    assert await redis_client.exists(COOLDOWN_KEY) == 0


# ------------------------------------------------------------------ listener


def mail(n: int) -> Message:
    msg = EmailMessage()
    msg["From"] = "payroll@abc.com"
    msg["Message-ID"] = f"<m{n}@abc.com>"
    msg.set_content(f"mail {n}")
    return msg


class FakeSource:
    """A second IMAP connection (ImapSource stand-in) over a fixed mailbox."""

    boxes: dict[int, Message] = {}
    entered = 0

    def __enter__(self) -> "FakeSource":
        FakeSource.entered += 1
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def status(self) -> tuple[int, int]:
        return 1, max(self.boxes, default=0) + 1

    def fetch_from_uid(self, start: int) -> list[tuple[int, Message]]:
        found = [(u, m) for u, m in sorted(self.boxes.items()) if u >= start]
        return found or [max(self.boxes.items())]

    def fetch_since(self, day: date) -> list[tuple[int, Message]]:
        return sorted(self.boxes.items())

    def mark_read(self, uid: int) -> None:
        pass


async def test_manual_check_reads_new_mail_and_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = {"<m2@abc.com>": "queued", "<m3@abc.com>": "ignored: sender not on any whitelist"}

    async def accept(email: Any) -> str:
        return outcomes[email.message_id]

    FakeSource.boxes = {1: mail(1), 2: mail(2), 3: mail(3)}
    monkeypatch.setattr(el, "ImapSource", FakeSource)
    monkeypatch.setattr(el, "accept_email", accept)
    cursor = Cursor(redis_client)
    await cursor.set(1, 1)  # mail 1 was read before

    request_id = str(uuid.uuid4())
    await el.manual_check(request_id, cursor)

    result = await read_result(redis_client, request_id)
    assert result is not None and result["state"] == "done"
    assert (result["found"], result["queued"], result["ignored"]) == (2, 1, 1)
    assert await cursor.get() == (1, 3)
    status = await redis_client.hgetall(STATUS_KEY)
    assert status["last_found"] == "2" and status["connected"] == "1"


async def test_manual_check_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    class Refused:
        def __enter__(self) -> "Refused":
            raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(el, "ImapSource", Refused)
    request_id = str(uuid.uuid4())
    await el.manual_check(request_id, Cursor(redis_client))
    result = await read_result(redis_client, request_id)
    assert result is not None and result["state"] == "failed"
    assert "Connection refused" in result["error"]


async def test_a_request_while_reconnecting_ends_the_wait() -> None:
    checks = el.ManualChecks(connected=False)
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    waiting = asyncio.create_task(el._sleep_or_wake(checks, 30))
    await asyncio.sleep(0.05)
    await el.handle_request(json.dumps({"request_id": request_id}), checks, Cursor(redis_client))
    await asyncio.wait_for(waiting, timeout=2)
    assert time.monotonic() - started < 2  # not the full 30 s
    assert checks.pending == [request_id]
    assert (await read_result(redis_client, request_id))["state"] == "running"  # type: ignore[index]

    await checks.resolve(Counter({"queued": 2}))  # the reconnect's catch-up answers
    done = await read_result(redis_client, request_id)
    assert done is not None and done["state"] == "done" and done["queued"] == 2
    assert checks.pending == [] and not checks.wake.is_set()


async def test_only_one_catch_up_at_a_time() -> None:
    order: list[str] = []

    async def holder(name: str) -> None:
        async with CatchUpLock(redis_client, poll_s=0.02):
            order.append(f"{name} in")
            await asyncio.sleep(0.15)
            order.append(f"{name} out")

    await asyncio.gather(holder("idle"), holder("manual"))
    assert order in (
        ["idle in", "idle out", "manual in", "manual out"],
        ["manual in", "manual out", "idle in", "idle out"],
    )
    assert await redis_client.exists(LOCK_KEY) == 0
