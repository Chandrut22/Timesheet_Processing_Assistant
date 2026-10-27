from typing import Literal

from pydantic import BaseModel


class MailboxStatus(BaseModel):
    """The email listener as the dashboard shows it (from its heartbeat in Redis)."""

    enabled: bool | None  # None = the listener never reported (not started yet)
    running: bool  # heartbeat younger than EMAIL_LISTENER_STALE_SECONDS
    connected: bool  # logged in to the mailbox right now
    mailbox: str | None  # the address it reads
    last_check_at: str | None  # ISO time of the last finished check
    last_found: int | None  # emails handled in that check
    last_queued: int | None
    last_ignored: int | None
    last_error: str | None
    cooldown_seconds: int  # seconds until "Check mail now" can be pressed again


class MailboxCheck(BaseModel):
    """One "Check mail now" request and, once done, what it found."""

    request_id: str
    state: Literal["queued", "running", "done", "failed"]
    requested_at: str | None = None
    requested_by: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    found: int | None = None  # emails handled
    queued: int | None = None  # saved and sent to the worker
    ignored: int | None = None  # unknown / unverified sender, nothing to read
    duplicates: int | None = None  # already received before
    failed: int | None = None  # could not be saved (recorded as failed)
    note: str | None = None
    error: str | None = None
