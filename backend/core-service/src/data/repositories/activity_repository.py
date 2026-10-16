import uuid
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import (
    AuditEvent,
    ProcessingStep,
    ReprocessRun,
    SubmissionStateChange,
    Timesheet,
)


class ActivityRepository:
    """Reads the state log, the step log and the audit events of one submission."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def states(self, submission_id: uuid.UUID) -> Sequence[SubmissionStateChange]:
        rows = await self.session.scalars(
            select(SubmissionStateChange)
            .where(SubmissionStateChange.submission_id == submission_id)
            .order_by(SubmissionStateChange.created_at, SubmissionStateChange.id)
        )
        return rows.all()

    async def steps(self, submission_id: uuid.UUID) -> Sequence[ProcessingStep]:
        rows = await self.session.scalars(
            select(ProcessingStep)
            .where(ProcessingStep.submission_id == submission_id)
            .order_by(ProcessingStep.created_at, ProcessingStep.id)
        )
        return rows.all()

    async def audit(self, submission_id: uuid.UUID) -> Sequence[AuditEvent]:
        timesheet_ids = select(Timesheet.id).where(Timesheet.submission_id == submission_id)
        rows = await self.session.scalars(
            select(AuditEvent)
            .where(
                or_(
                    and_(
                        AuditEvent.entity_type == "submission",
                        AuditEvent.entity_id == submission_id,
                    ),
                    and_(
                        AuditEvent.entity_type == "timesheet",
                        AuditEvent.entity_id.in_(timesheet_ids),
                    ),
                )
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return rows.all()

    async def reprocess_runs(self, submission_id: uuid.UUID) -> Sequence[ReprocessRun]:
        rows = await self.session.scalars(
            select(ReprocessRun)
            .where(ReprocessRun.submission_id == submission_id)
            .order_by(ReprocessRun.created_at, ReprocessRun.id)
        )
        return rows.all()
