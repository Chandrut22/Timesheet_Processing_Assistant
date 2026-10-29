"""The worker's side: claim a submission, classify its attachments from the email
(optional), read each file, extract timesheets, then match the employee, apply the pay
rules, check for duplicates and decide.

Every step is written to the step-by-step log (input, output, time, result) and the
submission's state moves Reading -> Matching -> Rule checks -> Awaiting review /
Approved, or Ignored / Failed, each change logged with its time.

Each document is committed on its own, so a failure halfway keeps the work already
done. A reprocess skips files that were already read (their text is saved), extracts
again and updates the existing timesheets in place (the earlier data is kept in
timesheet_versions).
When the job is a reprocess, every step is tagged with its run, and the run is closed
at the end with the AFTER snapshot (see reprocess.py).

This module only runs the stages in order and owns the job's deadline and failure
handling; each stage lives in src/core/services/pipeline/ (see its __init__)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    DocumentStatus,
    RefetchMode,
    SubmissionState,
    SubmissionStatus,
)
from src.core.services.activity_log import current_reprocess_run, set_state
from src.core.services.failures import JobTooSlowError, TooManyRunsError
from src.core.services.pipeline.claiming import CLAIMABLE, claim, claimable
from src.core.services.pipeline.classifying import (
    classify_by_metadata,
    skipped_by_classifier,
)
from src.core.services.pipeline.deciding import check_and_decide
from src.core.services.pipeline.extracting import extract_document
from src.core.services.pipeline.failing import RetryLater, record_failure
from src.core.services.pipeline.fetching import refetch_from_mailbox
from src.core.services.pipeline.finishing import already_extracted, finish
from src.core.services.pipeline.matching import CompanyContexts, match_timesheets
from src.core.services.pipeline.reading import friendly_read_error, read_document
from src.core.services.reprocess import finish_run
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal
from src.data.models import Company, Document, ReprocessRun, Submission
from src.observability.tracing.spans import pipeline_span, set_attributes

# Imported from here by the Celery task and older code: kept as this module's names.
__all__ = [
    "CLAIMABLE",
    "ProcessingService",
    "RetryLater",
    "claimable",
    "friendly_read_error",
    "process_submission_by_id",
]

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._contexts = CompanyContexts(session)

    async def process(
        self,
        submission_id: uuid.UUID,
        reprocess_run_id: uuid.UUID | None = None,
        retry_token: uuid.UUID | None = None,
    ) -> None:
        """Raises RetryLater after a temporary failure while runs are left."""
        token = current_reprocess_run.set(reprocess_run_id)
        try:
            with pipeline_span(
                "submission.process",
                submission_id=submission_id,
                reprocess_run_id=reprocess_run_id,
                scheduled_retry=retry_token is not None,
            ):
                await self._process(submission_id, reprocess_run_id, retry_token)
        finally:
            current_reprocess_run.reset(token)

    async def _process(
        self,
        submission_id: uuid.UUID,
        reprocess_run_id: uuid.UUID | None,
        retry_token: uuid.UUID | None,
    ) -> None:
        attempt = await claim(self.session, submission_id, retry_token)
        set_attributes(run=attempt, claimed=attempt is not None)
        if attempt is None:
            if retry_token is not None:
                logger.info("Retry for %s is no longer current; skipped", submission_id)
                return
            logger.info(
                "Submission %s already processed or missing; skipped", submission_id
            )
            current = await self.session.scalar(
                select(Submission.status).where(Submission.id == submission_id)
            )
            if current == SubmissionStatus.PROCESSING:
                # a second copy of a job another worker is running: leave it alone
                return
            if reprocess_run_id is not None:
                await finish_run(
                    self.session,
                    reprocess_run_id,
                    error="The reprocess could not start: the email was not waiting to "
                    "be processed.",
                )
                await self.session.commit()
            return
        run = (
            await self.session.get(ReprocessRun, reprocess_run_id)
            if reprocess_run_id is not None
            else None
        )
        only_document = run.document_id if run is not None else None
        refetch = RefetchMode(run.refetch) if run is not None and run.refetch else None

        submission = await self.session.get(
            Submission, submission_id, populate_existing=True
        )
        if submission is None:
            return
        company = (
            await self.session.get(Company, submission.company_id)
            if submission.company_id
            else None
        )

        try:
            if (
                attempt > settings.worker_max_attempts
            ):  # the worker kept dying on this job
                raise TooManyRunsError(attempt)
            limit = settings.worker_job_timeout_seconds
            deadline = asyncio.timeout(limit)
            try:
                async with deadline:
                    await self._steps(
                        submission, company, only_document, reprocess_run_id, refetch
                    )
            except TimeoutError as exc:
                if deadline.expired():  # our limit, not a timeout inside a library
                    raise JobTooSlowError(limit) from exc
                raise
        except Exception as exc:
            try:
                await self.session.rollback()
            except (
                Exception
            ):  # the timeout cut a database call short: drop the connection
                await self.session.invalidate()
            retry = await record_failure(
                self.session, submission_id, reprocess_run_id, attempt, exc
            )
            if retry is not None:
                raise retry from exc
            raise

    async def _steps(
        self,
        submission: Submission,
        company: Company | None,
        only_document: uuid.UUID | None,
        reprocess_run_id: uuid.UUID | None,
        refetch: RefetchMode | None = None,
    ) -> None:
        """(Fetch from the mailbox,) classify from the email, read, extract, match,
        rules, decide; then the final state."""
        # 0. A reprocess that needs the original email fetches it again first
        set_state(self.session, submission, SubmissionState.READING)
        if refetch is not None:
            with pipeline_span("submission.refetch", mode=refetch.value):
                await refetch_from_mailbox(
                    self.session, submission, refetch, only_document
                )
        await self.session.commit()

        # 1. The optional classifier, from the file names and the email only: an
        #    attachment it is sure is not a timesheet is left unread (file kept)
        await classify_by_metadata(self.session, submission, only_document)
        await self.session.commit()

        # 2. Read every file that is waiting (a reprocess also reads the ones the
        #    classifier skipped: a person asked for a full run)
        is_reprocess = current_reprocess_run.get() is not None
        for document in submission.documents:
            if document.status == DocumentStatus.PENDING and (
                not skipped_by_classifier(document)
                or (
                    is_reprocess
                    and (only_document is None or document.id == only_document)
                )
            ):
                with pipeline_span(
                    "document.read",
                    document_id=document.id,
                    file_type=PurePath(document.filename).suffix.lower() or None,
                    size_bytes=document.size_bytes,
                ) as span:
                    await read_document(self.session, document)
                    span.set_attribute("status", document.status)
                    span.set_attribute("characters", len(document.extracted_text or ""))
                    span.set_attribute("read_method", document.read_method or "")
                    if (
                        document.writing_class
                    ):  # photos / scans read by the vision model
                        span.set_attribute("writing_class", document.writing_class)
                        span.set_attribute("unclear_marks", document.unclear_marks)
                self._progress(submission)
                await self.session.commit()
                if document.status != DocumentStatus.PENDING:
                    await upload_buffer.delete_file(
                        document.id
                    )  # text saved: drop the bytes

        # 3. Extract, match, rules, decide - document by document
        for document in submission.documents:
            if only_document is not None and document.id != only_document:
                continue  # reprocess of one attachment: leave the others alone
            if skipped_by_classifier(document) and not is_reprocess:
                continue  # the email body the classifier is sure is not a timesheet
            if document.status == DocumentStatus.PARSED and not await already_extracted(
                self.session, document.id, reprocess_run_id
            ):
                with pipeline_span("document.extract", document_id=document.id):
                    await self._extract(submission, document, company)
                self._progress(submission)
                await self.session.commit()

        # 4. Final state (and close the reprocess run, in the same commit)
        await finish(self.session, submission)
        if reprocess_run_id is not None:
            await self.session.flush()
            await finish_run(self.session, reprocess_run_id)
        await self.session.commit()
        logger.info("Submission %s processed: %s", submission.id, submission.state)

    @staticmethod
    def _progress(submission: Submission) -> None:
        """Mark progress, so a long job with many files is never seen as abandoned."""
        submission.updated_at = datetime.now(UTC)

    async def _extract(
        self, submission: Submission, document: Document, company: Company | None
    ) -> None:
        """One read document: AI extraction, matching, rules, decision."""
        set_state(self.session, submission, SubmissionState.MATCHING)
        extraction = await extract_document(self.session, submission, document)
        if extraction is None:
            return  # no timesheet in it (already in the step log)

        # 1. Which company and which employee is each timesheet for?
        built = await match_timesheets(
            self.session, self._contexts, submission, document, extraction
        )

        # 2. Pay rules, assignment dates, duplicates, decision
        set_state(self.session, submission, SubmissionState.RULE_CHECKS)
        await check_and_decide(self.session, submission, document, built)

        logger.info(
            "Extracted %d timesheet(s) from %s",
            len(extraction.result.timesheets),
            document.filename,
        )


async def process_submission_by_id(
    submission_id: uuid.UUID,
    *,
    reprocess_run_id: uuid.UUID | None = None,
    retry_token: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        await ProcessingService(session).process(
            submission_id, reprocess_run_id, retry_token
        )
