import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.rbac.principal import Principal
from src.data.models import AuditEvent


def record_event(
    session: AsyncSession,
    *,
    entity_type: Literal["timesheet", "submission", "export", "import"],
    entity_id: uuid.UUID,
    action: str,
    actor: Principal | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the current transaction (saved by the caller's commit).
    actor=None means the system did it (the worker)."""
    session.add(
        AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else None,
            details=details or {},
        )
    )
