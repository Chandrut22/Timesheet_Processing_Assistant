"""A dropped IMAP connection (SSLEOFError while idling, seen in the email listener log)
is a one-line warning and a quick reconnect, not a traceback; anything else still backs
off. No network: the mailbox and the waits are fakes."""

import asyncio
import imaplib
import logging
import ssl
from typing import Any

import pytest

from src.config.settings import settings
from src.control.workers import email_listener as el
from src.handlers.email import imap_source
from src.handlers.email.imap_source import ImapSource, MailConnectionLost


class FakeIdle:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def wait(self, timeout: int) -> list[bytes]:
        raise self.error


class FakeMailbox:
    def __init__(self, error: BaseException) -> None:
        self.idle = FakeIdle(error)


def source_with(error: BaseException) -> ImapSource:
    source = ImapSource()
    source._mailbox = FakeMailbox(error)  # type: ignore[assignment]
    return source


@pytest.mark.parametrize(
    "error",
    [
        ssl.SSLEOFError(8, "EOF occurred in violation of protocol (_ssl.c:2503)"),
        ConnectionResetError(104, "Connection reset by peer"),
        TimeoutError("timed out"),
        imaplib.IMAP4.abort("socket error: EOF"),
        EOFError(),
    ],
)
def test_network_errors_from_imap_become_connection_lost(error: BaseException) -> None:
    with pytest.raises(MailConnectionLost) as caught:
        source_with(error).wait(120)
    assert caught.value.__cause__ is error
    assert type(error).__name__ in str(caught.value)


def test_other_errors_are_not_relabelled() -> None:
    with pytest.raises(ValueError):
        source_with(ValueError("a bug")).wait(120)


def test_delays() -> None:
    lost = MailConnectionLost("SSLEOFError: EOF")
    assert el.next_delay(lost, True, 5, since_last_quick=1e9) == 2  # first drop: at once
    assert el.next_delay(lost, True, 5, since_last_quick=10) == 5  # drops in a row: back off
    assert el.next_delay(lost, False, 40, since_last_quick=1e9) == 40  # never connected
    database_down = ConnectionRefusedError(111, "Connection refused")  # not from IMAP
    assert el.next_delay(database_down, True, 5, since_last_quick=1e9) == 5


def test_close_never_hangs_or_raises_on_a_dead_connection() -> None:
    class DeadClient:
        class sock:  # noqa: N801
            @staticmethod
            def settimeout(_: float) -> None:
                raise OSError("bad file descriptor")

        def shutdown(self) -> None:
            raise OSError("already closed")

    class DeadMailbox:
        client = DeadClient()

        def logout(self) -> None:
            raise ssl.SSLEOFError(8, "EOF")

    source = ImapSource()
    source._mailbox = DeadMailbox()  # type: ignore[assignment]
    source.__exit__(None, None, None)
    assert source._mailbox is None


def test_listener_logs_one_line_and_reconnects_quickly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Connect, catch up, idle -> SSLEOFError; then a reconnect after 2 s."""
    connects: list[int] = []
    sleeps: list[float] = []

    class Source:
        def __enter__(self) -> "Source":
            connects.append(1)
            return self

        def __exit__(self, *a: Any) -> None:
            pass

        def wait(self, timeout: int) -> bool:
            raise MailConnectionLost("SSLEOFError: EOF occurred in violation of protocol")

    async def caught_up(source: Any, cursor: Any) -> None:
        return None

    async def fake_sleep(checks: Any, seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError  # stop the endless loop

    async def nothing(*a: Any, **k: Any) -> None:
        return None

    async def no_watcher(*a: Any) -> None:
        await asyncio.Event().wait()  # like the real one: runs until cancelled

    monkeypatch.setattr(el, "ImapSource", Source)
    monkeypatch.setattr(el, "_catch_up", caught_up)
    monkeypatch.setattr(el, "_sleep_or_wake", fake_sleep)
    monkeypatch.setattr(el, "_beat", nothing)  # no Redis in unit tests
    monkeypatch.setattr(el, "_watch_requests", no_watcher)
    caplog.set_level(logging.INFO, logger="email_listener")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(el.run())

    assert sleeps == [2, 5]  # quick once, then back off: never a login every 2 s
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2 and "Mail server connection lost (SSLEOFError" in warnings[0].message
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert all(r.exc_info is None for r in warnings)  # no traceback
    assert len(connects) == 2


def test_settings_defaults() -> None:
    from src.config.settings import Settings

    defaults = Settings(_env_file=None)
    assert defaults.email_idle_timeout == 120 and defaults.imap_timeout_s == 60


def test_the_socket_timeout_is_passed_to_imap_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakeMailBoxClass:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            seen.update(host=host, port=port, timeout=timeout)

        def login(self, *a: Any, **k: Any) -> "FakeMailBoxClass":
            return self

    from pydantic import SecretStr

    monkeypatch.setattr(imap_source, "MailBox", FakeMailBoxClass)
    monkeypatch.setattr(settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(settings, "imap_user", "u@example.com")
    monkeypatch.setattr(settings, "imap_password", SecretStr("abcd efgh"))
    ImapSource().__enter__()
    assert seen["timeout"] == 60
