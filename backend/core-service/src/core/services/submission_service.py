import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import SubmissionStatus, TimesheetStatus
from src.control.workers.dispatch import enqueue_submission
from src.core.exceptions import ConflictError, NotFoundError
from src.core.rbac.principal import Principal
from src.core.services.audit import record_event
from src.data.models import Submission, Timesheet


class SubmissionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reprocess(self, submission_id: uuid.UUID, actor: Principal) -> Submission:
        """Throw away this submission's timesheets and run extraction again.
        Files already read are not read again (their text is saved)."""
        submission = await self.session.get(Submission, submission_id)
        if submission is None:
            raise NotFoundError("Submission not found.")
        if submission.status in (SubmissionStatus.RECEIVED, SubmissionStatus.PROCESSING):
            raise ConflictError("This submission is already queued or being processed.")

        timesheets = (
            await self.session.scalars(
                select(Timesheet).where(Timesheet.submission_id == submission_id)
            )
        ).all()
        if any(t.status == TimesheetStatus.EXPORTED for t in timesheets):
            raise ConflictError(
                "Some timesheets were already exported; this submission cannot be reprocessed."
            )

        for timesheet in timesheets:
            await self.session.delete(timesheet)
        submission.status = SubmissionStatus.RECEIVED
        submission.error = None
        submission.processed_at = None

        record_event(
            self.session,
            entity_type="submission",
            entity_id=submission.id,
            action="reprocessed",
            actor=actor,
            details={"deleted_timesheets": len(timesheets)},
        )
        await self.session.commit()
        await enqueue_submission(submission.id)
        await self.session.refresh(submission)
        return submission
