"""The worker's side: claim a submission, read each file, extract timesheets, save them.

Each document is committed on its own, so a failure halfway keeps the work already
done. A reprocess skips files that were already read (their text is saved) and
only re-runs extraction where no timesheets exist yet."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import DocumentStatus, SubmissionStatus
from src.control.agents.extraction_agent import extract_timesheets
from src.core.services.employee_matcher import (
    MatchResult,
    apply_match,
    match_employee,
    to_record,
)
from src.core.services.pay_rules import recalculate, rules_from_company
from src.core.services.timesheet_builder import BuildContext, build_timesheet
from src.data.clients import upload_buffer
from src.data.clients.document_reader import DocumentReadError, read_document
from src.data.clients.postgres import SessionLocal
from src.data.models import Company, Document, Submission, Timesheet
from src.data.repositories.employee_repository import EmployeeRepository
from src.data.repositories.holiday_repository import HolidayRepository

logger = logging.getLogger(__name__)

CLAIMABLE = (SubmissionStatus.RECEIVED, SubmissionStatus.PROCESSING, SubmissionStatus.FAILED)


class ProcessingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _claim(self, submission_id: uuid.UUID) -> bool:
        claimed = await self.session.scalar(
            update(Submission)
            .where(Submission.id == submission_id, Submission.status.in_(CLAIMABLE))
            .values(status=SubmissionStatus.PROCESSING, error=None)
            .returning(Submission.id)
        )
        await self.session.commit()
        return claimed is not None

    async def process(self, submission_id: uuid.UUID) -> None:
        if not await self._claim(submission_id):
            logger.info("Submission %s already processed or missing; skipped", submission_id)
            return

        submission = await self.session.get(Submission, submission_id, populate_existing=True)
        if submission is None:
            return
        company = (
            await self.session.get(Company, submission.company_id)
            if submission.company_id
            else None
        )

        try:
            for document in submission.documents:
                if document.status == DocumentStatus.PENDING:
                    await self._read(document)
                    await self.session.commit()
                    if document.status != DocumentStatus.PENDING:
                        await upload_buffer.delete_file(document.id)  # text saved: drop the bytes

                if document.status == DocumentStatus.PARSED and not await self._has_timesheets(
                    document.id
                ):
                    await self._extract(submission, document, company)
                    await self.session.commit()

            submission.status = SubmissionStatus.PROCESSED
            submission.processed_at = datetime.now(UTC)
            await self.session.commit()
            logger.info("Submission %s processed", submission_id)
        except Exception as exc:
            await self.session.rollback()
            await self.session.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(status=SubmissionStatus.FAILED, error=str(exc)[:2000])
            )
            await self.session.commit()
            logger.exception("Submission %s failed", submission_id)
            raise

    async def _read(self, document: Document) -> None:
        data = await upload_buffer.get_file(document.id)
        if data is None:
            document.status = DocumentStatus.FAILED
            document.error = "The file expired before it was processed. Upload it again."
            return
        try:
            # Docling is CPU-heavy and blocking: run it off the event loop.
            text = await asyncio.to_thread(read_document, document.filename, data)
        except DocumentReadError as exc:
            document.status = DocumentStatus.FAILED
            document.error = str(exc)[:2000]
            return
        document.extracted_text = text
        document.status = DocumentStatus.PARSED
        document.error = None
        logger.info("Read %s: %d characters", document.filename, len(text))

    async def _has_timesheets(self, document_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Timesheet.id).where(Timesheet.document_id == document_id).limit(1)
        )
        return found is not None

    async def _extract(
        self, submission: Submission, document: Document, company: Company | None
    ) -> None:
        result = await extract_timesheets(
            document_text=document.extracted_text or "",
            filename=document.filename,
            received_at=submission.received_at,
            email_subject=submission.subject,
            email_body=submission.body_text,
        )
        if not result.timesheets:
            document.error = "No timesheet found in this document."
            return

        ctx = BuildContext(
            submission_id=submission.id,
            document_id=document.id,
            company_id=submission.company_id,
            received_on=submission.received_at.date(),
            week_start_day=company.week_start if company else 0,
        )

        rules = rules_from_company(company)
        holidays = await HolidayRepository(self.session).dates_for(submission.company_id)
        employees = (
            [to_record(e) for e in await EmployeeRepository(self.session).list_active(company.id)]
            if company
            else []
        )

        for extracted in result.timesheets:
            timesheet = build_timesheet(extracted, ctx)
            if company:
                match = match_employee(
                    timesheet.extracted_name, timesheet.extracted_code, employees
                )
                apply_match(timesheet, match)
            else:
                apply_match(timesheet, MatchResult(None, None), company_known=False)
            recalculate(timesheet, rules, holidays, default_rules_used=company is None)
            self.session.add(timesheet)
        logger.info("Extracted %d timesheet(s) from %s", len(result.timesheets), document.filename)


async def process_submission_by_id(submission_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        await ProcessingService(session).process(submission_id)
