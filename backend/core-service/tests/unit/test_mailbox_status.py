"""build_status(): the email listener's heartbeat as the dashboard shows it (pure)."""

import time

import pytest

from src.config.settings import settings
from src.core.services.mailbox_service import build_status

NOW = time.time()


def beat(age_s: float, **fields: str) -> dict[str, str]:
    return {"alive_at": str(NOW - age_s), "enabled": "1", "connected": "1", **fields}


def test_a_fresh_heartbeat_is_running_and_connected() -> None:
    s = build_status(
        beat(
            30,
            last_check_at="2026-10-27T09:00:00+00:00",
            last_found="3",
            last_queued="2",
            last_ignored="1",
            mailbox="inbox@x.example",
        ),
        0,
        NOW,
    )
    assert s.running and s.connected and s.enabled
    assert (s.last_found, s.last_queued, s.last_ignored) == (3, 2, 1)
    assert s.mailbox == "inbox@x.example" and s.last_error is None


def test_a_stale_heartbeat_is_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_listener_stale_seconds", 300)
    s = build_status(beat(301, last_error="Mail server connection lost"), 0, NOW)
    assert not s.running and not s.connected
    assert s.last_error == "Mail server connection lost"


def test_waiting_to_reconnect_is_running_but_not_connected() -> None:
    s = build_status(beat(10, connected="0"), 0, NOW)
    assert s.running and not s.connected


def test_never_started_and_turned_off() -> None:
    never = build_status({}, 0, NOW)
    assert never.enabled is None and not never.running
    off = build_status({"enabled": "0", "alive_at": str(NOW)}, 0, NOW)
    assert off.enabled is False and not off.running


def test_cooldown_is_never_negative() -> None:
    assert build_status(beat(1), -2, NOW).cooldown_seconds == 0
    assert build_status(beat(1), 17, NOW).cooldown_seconds == 17


def test_defaults() -> None:
    from src.config.settings import Settings

    d = Settings(_env_file=None)
    assert d.email_manual_check_cooldown_seconds == 30 and d.email_listener_stale_seconds == 300
