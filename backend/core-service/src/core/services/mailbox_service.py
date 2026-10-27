"""The API side of "Check mail now": the listener's status, starting a manual check, and
reading its result. The listener's side is control/workers/email_listener.py; the Redis
keys they share are in data/clients/mailbox_signals.py."""

import json
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    TooManyRequestsError,
)
from src.core.rbac.principal import Principal
from src.core.services.audit import record_event
from src.data.clients.mailbox_signals import (
    CHECK_CHANNEL,
    COOLDOWN_KEY,
    now_iso,
    read_result,
    read_status,
    update_result,
)
from src.schemas.email import MailboxCheck, MailboxStatus


class EmailListenerDownError(ServiceUnavailableError):
    code = "email_listener_down"


class CheckCooldownError(TooManyRequestsError):
    code = "check_cooldown"


def _number(raw: str | None) -> float | None:
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _int(raw: str | None) -> int | None:
    value = _number(raw)
    return int(value) if value is not None else None


def build_status(raw: dict[str, str], cooldown_left: int, now: float) -> MailboxStatus:
    """Pure: the heartbeat hash as the dashboard shows it."""
    alive_at = _number(raw.get("alive_at"))
    enabled = None if "enabled" not in raw else raw["enabled"] == "1"
    running = (
        enabled is not False
        and alive_at is not None
        and now - alive_at <= settings.email_listener_stale_seconds
    )
    return MailboxStatus(
        enabled=enabled,
        running=running,
        connected=running and raw.get("connected") == "1",
        mailbox=raw.get("mailbox") or None,
        last_check_at=raw.get("last_check_at") or None,
        last_found=_int(raw.get("last_found")),
        last_queued=_int(raw.get("last_queued")),
        last_ignored=_int(raw.get("last_ignored")),
        last_error=raw.get("last_error") or None,
        cooldown_seconds=max(0, cooldown_left),
    )


class MailboxService:
    def __init__(self, session: AsyncSession, redis: Any) -> None:
        self.session = session
        self.redis = redis

    async def status(self) -> MailboxStatus:
        raw = await read_status(self.redis)
        ttl = await self.redis.ttl(COOLDOWN_KEY)
        return build_status(raw, int(ttl) if ttl and ttl > 0 else 0, time.time())

    async def request_check(self, actor: Principal) -> MailboxCheck:
        status = await self.status()
        if status.enabled is False:
            raise ConflictError("Reading email is turned off (EMAIL_ENABLED=false).")
        if not status.running:
            raise EmailListenerDownError(
                "The email listener is not running, so it cannot check the mailbox now."
            )
        cooldown = settings.email_manual_check_cooldown_seconds
        if not await self.redis.set(COOLDOWN_KEY, "1", nx=True, ex=cooldown):
            left = max(1, int(await self.redis.ttl(COOLDOWN_KEY) or 1))
            raise CheckCooldownError(
                f"The mailbox was checked a moment ago. Try again in {left} seconds.",
                headers={"Retry-After": str(left)},
            )

        request_id = str(uuid.uuid4())
        await update_result(
            self.redis,
            request_id,
            state="queued",
            requested_at=now_iso(),
            requested_by=actor.name,
        )
        listeners = await self.redis.publish(CHECK_CHANNEL, json.dumps({"request_id": request_id}))
        if not listeners:  # nobody subscribed: the listener is gone after all
            await self.redis.delete(COOLDOWN_KEY)
            await update_result(self.redis, request_id, state="failed", error="No listener")
            raise EmailListenerDownError(
                "The email listener is not running, so it cannot check the mailbox now."
            )

        record_event(
            self.session,
            entity_type="mailbox",
            entity_id=uuid.UUID(request_id),
            action="email_check_requested",
            actor=actor,
            details={"mailbox": status.mailbox},
        )
        await self.session.commit()
        return await self.check(request_id)

    async def check(self, request_id: str) -> MailboxCheck:
        record = await read_result(self.redis, request_id)
        if record is None:
            raise NotFoundError("This mailbox check is unknown or too old.")
        return MailboxCheck.model_validate(record)
