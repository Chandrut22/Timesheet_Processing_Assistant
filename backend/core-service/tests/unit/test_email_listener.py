"""The cursor logic, with a fake mailbox and a fake Redis (no network)."""

import asyncio
from datetime import date
from email.message import EmailMessage, Message
from typing import Any

import pytest

from src.config.settings import settings
from src.handlers.email.listener import Cursor, process_new_mail
from src.handlers.email.parser import ParsedEmail


def mail(n: int) -> Message:
    msg = EmailMessage()
    msg["From"] = "payroll@abc.com"
    msg["Message-ID"] = f"<m{n}@abc.com>"
    msg.set_content(f"mail {n}")
    return msg


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, mapping: dict[str, Any]) -> None:
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, "0")) + amount)
        return int(bucket[field])

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def hdel(self, key: str, field: str) -> None:
        self.hashes.get(key, {}).pop(field, None)


class FakeMailbox:
    def __init__(self, uids: list[int], validity: int = 1) -> None:
        self.messages = {uid: mail(uid) for uid in uids}
        self.validity = validity
        self.since_calls: list[date] = []

    def status(self) -> tuple[int, int]:
        return self.validity, max(self.messages, default=0) + 1

    def fetch_from_uid(self, start_uid: int) -> list[tuple[int, Message]]:
        found = [(u, m) for u, m in sorted(self.messages.items()) if u >= start_uid]
        # Real IMAP: "n:*" returns the last message even when n is past the end
        return found or [max(self.messages.items())]

    def fetch_since(self, day: date) -> list[tuple[int, Message]]:
        self.since_calls.append(day)
        return sorted(self.messages.items())


class Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.ids: list[str] = []
        self.fail_on = fail_on

    async def __call__(self, email: ParsedEmail) -> str:
        if email.message_id == self.fail_on:
            raise RuntimeError("database down")
        self.ids.append(email.message_id)
        return "queued"


def run(source: FakeMailbox, cursor: Cursor, intake: Recorder, limit: int = 50) -> int:
    return asyncio.run(process_new_mail(source, cursor, intake, batch_limit=limit))


def test_first_run_new_only_sets_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    assert run(FakeMailbox([1, 2, 3]), cursor, intake) == 0
    assert intake.ids == []
    assert asyncio.run(cursor.get()) == (1, 3)  # old mail is left alone


def test_new_mail_after_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    box = FakeMailbox([1, 2])
    run(box, cursor, intake)  # first run: cursor at 2
    box.messages[3], box.messages[4] = mail(3), mail(4)
    run(box, cursor, intake)
    assert intake.ids == ["<m3@abc.com>", "<m4@abc.com>"]
    assert asyncio.run(cursor.get()) == (1, 4)


def test_nothing_new_does_not_reprocess_last_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    box = FakeMailbox([1, 2])
    run(box, cursor, intake)
    run(box, cursor, intake)
    assert intake.ids == []


def test_backfill_reads_recent_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "backfill")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    box = FakeMailbox([5, 6])
    run(box, cursor, intake)
    assert intake.ids == ["<m5@abc.com>", "<m6@abc.com>"]
    assert len(box.since_calls) == 1
    assert asyncio.run(cursor.get()) == (1, 6)


def test_uidvalidity_change_rescans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    asyncio.run(cursor.set(1, 99))
    box = FakeMailbox([1, 2], validity=2)  # folder renumbered
    run(box, cursor, intake)
    assert intake.ids == ["<m1@abc.com>", "<m2@abc.com>"]  # the DB skips real duplicates
    assert asyncio.run(cursor.get()) == (2, 2)


def test_failure_keeps_cursor_before_the_failed_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    redis = FakeRedis()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    box = FakeMailbox([1])
    run(box, cursor, Recorder())
    box.messages.update({2: mail(2), 3: mail(3)})
    with pytest.raises(RuntimeError):
        run(box, cursor, Recorder(fail_on="<m3@abc.com>"))
    assert asyncio.run(cursor.get()) == (1, 2)  # mail 3 will be tried again
    retry = Recorder()
    run(box, cursor, retry)
    assert retry.ids == ["<m3@abc.com>"]


def test_full_backfill_batch_leaves_cursor_at_last_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "backfill")
    redis, intake = FakeRedis(), Recorder()
    cursor = Cursor(redis)  # type: ignore[arg-type]
    box = FakeMailbox([1, 2, 3])
    box.fetch_since = lambda day: sorted(box.messages.items())[:2]  # type: ignore[method-assign]
    assert run(box, cursor, intake, limit=2) == 2
    assert asyncio.run(cursor.get()) == (1, 2)  # mail 3 comes in the next round
    run(box, cursor, intake, limit=2)
    assert intake.ids[-1] == "<m3@abc.com>"


class BrokenData(Exception):
    """Stands in for data the database refuses (not a connection problem)."""


class DbDown(ConnectionError):
    pass


class Failing:
    def __init__(self, bad: str, error: Exception) -> None:
        self.bad, self.error = bad, error
        self.ids: list[str] = []

    async def __call__(self, email: ParsedEmail) -> str:
        if email.message_id == self.bad:
            raise self.error
        self.ids.append(email.message_id)
        return "queued"


def test_a_bad_email_is_skipped_after_3_tries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    monkeypatch.setattr(settings, "email_max_intake_failures", 3)
    cursor = Cursor(FakeRedis())  # type: ignore[arg-type]
    box = FakeMailbox([1])
    run(box, cursor, Recorder())
    box.messages.update({2: mail(2), 3: mail(3)})
    intake = Failing("<m2@abc.com>", BrokenData("invalid byte sequence"))
    skipped: list[tuple[str, str]] = []

    async def give_up(email: ParsedEmail | None, ref: str, reason: str) -> None:
        skipped.append((email.message_id if email else "?", reason))

    for _ in range(2):  # tries 1 and 2: the cursor waits before mail 2
        with pytest.raises(BrokenData):
            asyncio.run(process_new_mail(box, cursor, intake, batch_limit=50, give_up=give_up))
        assert asyncio.run(cursor.get()) == (1, 1)
    asyncio.run(process_new_mail(box, cursor, intake, batch_limit=50, give_up=give_up))
    assert [s[0] for s in skipped] == ["<m2@abc.com>"]  # recorded as failed
    assert "after 3 tries" in skipped[0][1]
    assert intake.ids == ["<m3@abc.com>"]  # the inbox goes on
    assert asyncio.run(cursor.get()) == (1, 3)


def test_database_down_never_skips_an_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_start_from", "new")
    monkeypatch.setattr(settings, "email_max_intake_failures", 3)
    cursor = Cursor(FakeRedis())  # type: ignore[arg-type]
    box = FakeMailbox([1])
    run(box, cursor, Recorder())
    box.messages[2] = mail(2)
    intake = Failing("<m2@abc.com>", DbDown("connection refused"))
    for _ in range(5):
        with pytest.raises(DbDown):
            asyncio.run(process_new_mail(box, cursor, intake, batch_limit=50))
    assert asyncio.run(cursor.get()) == (1, 1)  # still waiting for the database
