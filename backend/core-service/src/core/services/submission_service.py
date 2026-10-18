"""Reprocess an email / upload, or one attachment of it, with a reason.

Nothing is deleted: the timesheets being replaced get status "superseded" and stay
visible in the history; the worker then extracts, matches and checks the document(s)
again with the CURRENT master data (employees, aliases, rates, holidays).
Files are read once; a reprocess uses the text saved from the first read."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import (
    DocumentStatus,
    ReprocessStatus,
    SubmissionSource,
    SubmissionState,
    SubmissionStatus,
    TimesheetStatus,
)
from src.control.workers.dispatch import enqueue_submission
from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.activity_log import set_state
from src.core.services.audit import record_event
from src.core.services.reprocess import finish_run, snapshot
from src.core.services.sweeper import is_stuck
from src.data.models import Document, ReprocessRun, Submission, Timesheet
from src.data.repositories.company_repository import WhitelistRepository


class SubmissionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _locked(self, submission_id: uuid.UUID) -> Submission:
        submission = await self.session.scalar(
            select(Submission).where(Submission.id == submission_id).with_for_update()
        )
        if submission is None:
            raise NotFoundError("Submission not found.")
        return submission

    async def runs(self, submission_id: uuid.UUID) -> Sequence[ReprocessRun]:
        if await self.session.get(Submission, submission_id) is None:
            raise NotFoundError("Submission not found.")
        rows = await self.session.scalars(
            select(ReprocessRun)
            .where(ReprocessRun.submission_id == submission_id)
            .order_by(ReprocessRun.created_at, ReprocessRun.id)
        )
        return rows.all()

    async def reprocess(
        self,
        submission_id: uuid.UUID,
        reason: str,
        actor: Principal,
        *,
        document_id: uuid.UUID | None = None,
    ) -> ReprocessRun:
        reason = reason.strip()
        if len(reason) < 3:
            raise ValidationFailedError("Enter a reason for reprocessing (at least 3 characters).")

        submission = await self._locked(submission_id)  # one request at a time

        # --- can it be reprocessed? -------------------------------------------------
        if submission.status in (
            SubmissionStatus.RECEIVED,
            SubmissionStatus.PROCESSING,
        ) and not is_stuck(submission, datetime.now(UTC)):
            raise ConflictError("This email is already queued or being processed. Try again later.")
        if submission.status == SubmissionStatus.IGNORED:
            raise ConflictError(
                "This email was ignored when it arrived "
                f"({submission.state_reason or 'sender not accepted'}), so its attachments "
                "were never saved. Fix the cause (e.g. add the sender to the whitelist) and "
                "ask the sender to send it again."
            )
        running = await self.session.scalar(
            select(ReprocessRun.id).where(
                ReprocessRun.submission_id == submission_id,
                ReprocessRun.status == ReprocessStatus.RUNNING,
            )
        )
        if running is not None:
            raise ConflictError("A reprocess of this email is already running.")

        documents: list[Document] = list(submission.documents)
        if document_id is not None:
            documents = [d for d in documents if d.id == document_id]
            if not documents:
                raise NotFoundError("Attachment not found in this email.")
            if documents[0].status != DocumentStatus.PARSED:
                raise ConflictError(
                    f"'{documents[0].filename}' was never read successfully "
                    f"({documents[0].error or documents[0].status}), and the file is no longer "
                    "stored. Ask the sender for a new copy or upload it again."
                )
        readable = [
            d for d in documents if d.status in (DocumentStatus.PARSED, DocumentStatus.PENDING)
        ]
        if not readable:
            raise ConflictError(
                "Nothing to reprocess: no attachment of this email could be read, and the files "
                "are no longer stored. Ask the sender for new copies or upload them again."
            )

        # --- the timesheets being replaced --------------------------------------------
        query = select(Timesheet).where(
            Timesheet.submission_id == submission_id,
            Timesheet.status != TimesheetStatus.SUPERSEDED,
        )
        if document_id is not None:
            query = query.where(Timesheet.document_id == document_id)
        current = (await self.session.scalars(query.order_by(Timesheet.created_at))).all()
        exported = [t for t in current if t.status == TimesheetStatus.EXPORTED]
        if exported:
            raise ConflictError(
                f"{len(exported)} timesheet(s) were already exported to payroll, so they cannot "
                "be replaced. Reprocessing is not possible."
                if document_id is None
                else "A timesheet from this attachment was already exported to payroll, so it "
                "cannot be replaced."
            )

        # --- start the run --------------------------------------------------------------
        run = ReprocessRun(
            id=uuid.uuid4(),
            submission_id=submission.id,
            document_id=document_id,
            reason=reason,
            requested_by_id=actor.id,
            requested_by_name=actor.name,
            status=ReprocessStatus.RUNNING,
            before_result=snapshot(submission.state, current),
        )
        self.session.add(run)
        for timesheet in current:  # kept, just no longer the live version
            timesheet.status = TimesheetStatus.SUPERSEDED
        company_before = submission.company_id
        if submission.source == SubmissionSource.EMAIL and submission.sender_email:
            found = await WhitelistRepository(self.session).find_company_id_for_sender(
                submission.sender_email
            )
            if found is not None:
                submission.company_id = found
        submission.status = SubmissionStatus.RECEIVED  # lets the worker claim it again
        submission.error = None
        # A new job: runs counted from zero, and any scheduled retry becomes stale.
        submission.attempts = 0
        submission.retry_at = None
        submission.retry_token = None
        submission.processed_at = None
        scope = documents[0].filename if document_id is not None else "the whole email"
        set_state(
            self.session,
            submission,
            SubmissionState.REPROCESSING,
            reason=f"Reprocess of {scope}: {reason}",
            actor=actor,
        )
        record_event(
            self.session,
            entity_type="submission",
            entity_id=submission.id,
            action="reprocessed",
            actor=actor,
            details={
                "reprocess_run_id": str(run.id),
                "reason": reason,
                "document_id": str(document_id) if document_id else None,
                "superseded_timesheets": [str(t.id) for t in current],
                "company_changed": submission.company_id != company_before,
            },
        )
        await self.session.commit()
        try:
            await enqueue_submission(submission.id, reprocess_run_id=run.id)
        except Exception:
            # Queue (Redis) down: close the run and say so, instead of leaving it "running".
            await self._queue_failed(submission.id, run.id)
            raise
        await self.session.refresh(run)
        return run

    async def _queue_failed(self, submission_id: uuid.UUID, run_id: uuid.UUID) -> None:
        message = "The job queue is not available. Try the reprocess again in a minute."
        submission = await self.session.get(Submission, submission_id, populate_existing=True)
        run = await self.session.get(ReprocessRun, run_id, populate_existing=True)
        if run is not None:
            # Nothing ran: give the timesheets back their earlier status.
            for item in run.before_result.get("timesheets", []):
                old = await self.session.get(Timesheet, uuid.UUID(item["id"]))
                if old is not None and old.status == TimesheetStatus.SUPERSEDED:
                    old.status = item["status"]
            await finish_run(self.session, run.id, error=message)
        if submission is not None:
            submission.status = SubmissionStatus.FAILED
            submission.error = message
            set_state(self.session, submission, SubmissionState.FAILED, reason=message)
        await self.session.commit()
