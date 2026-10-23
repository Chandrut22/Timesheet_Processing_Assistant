import uuid
from typing import Literal

from fastapi import APIRouter

from src.api.rest.dependencies import Reviewer, SessionDep
from src.data.repositories.audit_repository import AuditRepository
from src.schemas.review import AuditEventRead

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("")
async def list_audit_events(
    session: SessionDep,
    _: Reviewer,
    entity_type: Literal["timesheet", "submission", "employee", "company", "holiday"],
    entity_id: uuid.UUID,
) -> list[AuditEventRead]:
    events = await AuditRepository(session).for_entity(entity_type, entity_id)
    return [AuditEventRead.model_validate(e) for e in events]
