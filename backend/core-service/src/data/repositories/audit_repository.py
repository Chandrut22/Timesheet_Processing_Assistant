import uuid
from collections.abc import Sequence

from sqlalchemy import select

from src.data.models import AuditEvent
from src.data.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditEvent]):
    model = AuditEvent

    async def for_entity(
        self, entity_type: str, entity_id: uuid.UUID, limit: int = 100
    ) -> Sequence[AuditEvent]:
        rows = await self.session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return rows.all()
