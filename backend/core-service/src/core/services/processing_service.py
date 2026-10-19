"""The worker's side: claim a submission, read each file, extract timesheets, then
match the employee, apply the pay rules, check for duplicates and decide.

Every step is written to the step-by-step log (input, output, time, result) and the
submission's state moves Reading -> Matching -> Rule checks -> Awaiting review /
Approved, or Ignored / Failed, each change logged with its time.

Each document is committed on its own, so a failure halfway keeps the work already
done. A reprocess skips files that were already read (their text is saved) and only
re-runs extraction where no live timesheets exist (the replaced ones are "superseded").
When the job is a reprocess, every step is tagged with its run, and the run is closed
at the end with the AFTER snapshot (see reprocess.py)."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePath

from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import (
    DocumentStatus,
    StepName,
    StepResult,
    SubmissionState,
    SubmissionStatus,
    TimesheetStatus,
)
from src.control.agents.extraction_agent import extract_timesheets
from src.core.services.activity_log import (
    Stopwatch,
    current_reprocess_run,
    record_step,
    set_state,
    state_from_timesheets,
)
from src.core.services.audit import record_event
from src.core.services.company_matcher import CompanyRecord, decide_company
from src.core.services.email_intake_service import BODY_FILENAME
from src.core.services.employee_matcher import (
    EmployeeRecord,
    MatchResult,
    apply_match,
    match_employee,
    to_record,
)
from src.core.services.failures import (
    JobTooSlowError,
    TooManyRunsError,
    explain,
    plan_retry,
    technical_details,
)
from src.core.services.pay_rules import PayRules, recalculate, rules_from_company
from src.core.services.reprocess import finish_run, next_version
from src.core.services.timesheet_builder import BuildContext, build_timesheets, truncation_flag
from src.core.services.timesheet_validation import (
    can_auto_approve,
    check_assignment,
    lock_employee_weeks,
    validate_duplicates,
)
from src.data.clients import upload_buffer
from src.data.clients.document_reader import DocumentReadError, read_document
from src.data.clients.postgres import SessionLocal
from src.data.models import Company, Document, Employee, ReprocessRun, Submission, Timesheet
from src.data.repositories.employee_repository import EmployeeRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.observability.tracing.spans import (
    finished_span,
    now_ns,
    pipeline_span,
    set_attributes,
)
from src.utils.text import db_safe

logger = logging.getLogger(__name__)

CLAIMABLE = (SubmissionStatus.RECEIVED, SubmissionStatus.FAILED)


def claimable(now: datetime) -> ColumnElement[bool]:
    """Waiting or failed, or "processing" with no progress for worker_stale_after_seconds
    (its worker died). A job that is really running is never taken over: a second copy
    of the same job (queued twice, or handed out again by Redis) finds nothing to do."""
    stale = now - timedelta(seconds=settings.worker_stale_after_seconds)
    return or_(
        Submission.status.in_(CLAIMABLE),
        and_(Submission.status == SubmissionStatus.PROCESSING, Submission.updated_at < stale),
    )


class RetryLater(Exception):  # noqa: N818 - a signal to the task, not an error
    """A temporary failure: the task should run again after delay_seconds, carrying the
    token (only that scheduled run may pick the submission up)."""

    def __init__(self, token: uuid.UUID, delay_seconds: int) -> None:
        super().__init__(f"retry in {delay_seconds}s")
        self.token = token
        self.delay_seconds = delay_seconds


def friendly_read_error(filename: str, exc: Exception) -> str:
    """A message a reviewer can act on; the technical text goes to error_details."""
    text = str(exc).lower()
    if "password" in text or "encrypt" in text:
        return f"'{filename}' is password-protected. Ask the sender for an unlocked copy."
    if "could not load document" in text or "conversion failed" in text:
        return f"'{filename}' is damaged or not a valid file. Ask the sender to resend it."
    return f"Could not read '{filename}'. Ask the sender to resend it."


@dataclass(slots=True)
class _CompanyContext:
    """Everything the rules need for one company, loaded once per document."""

    company: Company | None
    rules: PayRules
    holidays: set[date]
    records: list[EmployeeRecord]  # for matching
    by_id: dict[uuid.UUID, EmployeeRecord]
    employees: dict[uuid.UUID, Employee]  # for assignment dates


def _gross(timesheet: Timesheet) -> float | None:
    parts = (
        timesheet.regular_amount,
        timesheet.overtime_amount,
        timesheet.double_time_amount,
        timesheet.holiday_amount,
    )
    if any(p is None for p in parts):
        return None
    return float(sum(p for p in parts if p is not None))


class ProcessingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._contexts: dict[uuid.UUID | None, _CompanyContext] = {}

    async def _company_records(self) -> dict[uuid.UUID, CompanyRecord]:
        rows = await self.session.scalars(select(Company).where(Company.is_active.is_(True)))
        return {c.id: CompanyRecord(c.id, c.name, tuple(c.aliases or ())) for c in rows.all()}

    async def _company_context(self, company_id: uuid.UUID | None) -> _CompanyContext:
        if company_id not in self._contexts:
            company = await self.session.get(Company, company_id) if company_id else None
            active = (
                await EmployeeRepository(self.session).list_active(company.id) if company else []
            )
            records = [to_record(e) for e in active]
            self._contexts[company_id] = _CompanyContext(
                company=company,
                rules=rules_from_company(company),
                holidays=set(await HolidayRepository(self.session).dates_for(company_id)),
                records=records,
                by_id={r.id: r for r in records},
                employees={e.id: e for e in active},
            )
        return self._contexts[company_id]

    async def _claim(self, submission_id: uuid.UUID, retry_token: uuid.UUID | None) -> int | None:
        """Take the submission for this run; returns the run number (1, 2, ...) or None.
        A scheduled retry only claims it while its token is still the current one, so a
        retry made stale by a reprocess does nothing."""
        query = update(Submission).where(
            Submission.id == submission_id, claimable(datetime.now(UTC))
        )
        if retry_token is not None:
            query = query.where(Submission.retry_token == retry_token)
        attempt = await self.session.scalar(
            query.values(
                status=SubmissionStatus.PROCESSING,
                error=None,
                attempts=Submission.attempts + 1,
                retry_at=None,
                retry_token=None,
                updated_at=datetime.now(UTC),  # the claim is progress (see claimable)
            ).returning(Submission.attempts)
        )
        await self.session.commit()
        return attempt

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
        attempt = await self._claim(submission_id, retry_token)
        set_attributes(run=attempt, claimed=attempt is not None)
        if attempt is None:
            if retry_token is not None:
                logger.info("Retry for %s is no longer current; skipped", submission_id)
                return
            logger.info("Submission %s already processed or missing; skipped", submission_id)
            current = await self.session.scalar(
                select(Submission.status).where(Submission.id == submission_id)
            )
            if current == SubmissionStatus.PROCESSING:
                return  # a second copy of a job another worker is running: leave it alone
            if reprocess_run_id is not None:
                await finish_run(
                    self.session,
                    reprocess_run_id,
                    error="The reprocess could not start: the email was not waiting "
                    "to be processed.",
                )
                await self.session.commit()
            return
        run = (
            await self.session.get(ReprocessRun, reprocess_run_id)
            if reprocess_run_id is not None
            else None
        )
        only_document = run.document_id if run is not None else None

        submission = await self.session.get(Submission, submission_id, populate_existing=True)
        if submission is None:
            return
        company = (
            await self.session.get(Company, submission.company_id)
            if submission.company_id
            else None
        )

        try:
            if attempt > settings.worker_max_attempts:  # the worker kept dying on this job
                raise TooManyRunsError(attempt)
            limit = settings.worker_job_timeout_seconds
            deadline = asyncio.timeout(limit)
            try:
                async with deadline:
                    await self._steps(submission, company, only_document, reprocess_run_id)
            except TimeoutError as exc:
                if deadline.expired():  # our limit, not a timeout inside a library
                    raise JobTooSlowError(limit) from exc
                raise
        except Exception as exc:
            try:
                await self.session.rollback()
            except Exception:  # the timeout cut a database call short: drop the connection
                await self.session.invalidate()
            retry = await self._fail(submission_id, reprocess_run_id, attempt, exc)
            if retry is not None:
                raise retry from exc
            raise

    async def _steps(
        self,
        submission: Submission,
        company: Company | None,
        only_document: uuid.UUID | None,
        reprocess_run_id: uuid.UUID | None,
    ) -> None:
        """Read, extract, match, rules, decide; then the final state."""
        # 1. Read every file that is waiting
        set_state(self.session, submission, SubmissionState.READING)
        await self.session.commit()
        for document in submission.documents:
            if document.status == DocumentStatus.PENDING:
                with pipeline_span(
                    "document.read",
                    document_id=document.id,
                    file_type=PurePath(document.filename).suffix.lower() or None,
                    size_bytes=document.size_bytes,
                ) as span:
                    await self._read(document)
                    span.set_attribute("status", document.status)
                    span.set_attribute("characters", len(document.extracted_text or ""))
                self._progress(submission)
                await self.session.commit()
                if document.status != DocumentStatus.PENDING:
                    await upload_buffer.delete_file(document.id)  # text saved: drop the bytes

        # 2. Extract, match, rules, decide - document by document
        for document in submission.documents:
            if only_document is not None and document.id != only_document:
                continue  # reprocess of one attachment: leave the others alone
            if document.status == DocumentStatus.PARSED and not await self._has_timesheets(
                document.id
            ):
                with pipeline_span("document.extract", document_id=document.id):
                    await self._extract(submission, document, company)
                self._progress(submission)
                await self.session.commit()

        # 3. Final state (and close the reprocess run, in the same commit)
        await self._finish(submission)
        if reprocess_run_id is not None:
            await self.session.flush()
            await finish_run(self.session, reprocess_run_id)
        await self.session.commit()
        logger.info("Submission %s processed: %s", submission.id, submission.state)

    @staticmethod
    def _progress(submission: Submission) -> None:
        """Mark progress, so a long job with many files is never seen as abandoned."""
        submission.updated_at = datetime.now(UTC)

    async def _fail(
        self,
        submission_id: uuid.UUID,
        reprocess_run_id: uuid.UUID | None,
        attempt: int,
        exc: Exception,
    ) -> RetryLater | None:
        """Record the failure in plain words and decide: try again later, or stop.
        The technical error goes to the processing log only."""
        failure = explain(exc)
        most = settings.worker_max_attempts
        plan = plan_retry(
            failure,
            attempt,
            max_attempts=most,
            base_delay=settings.worker_retry_delay_seconds,
        )
        token = uuid.uuid4() if plan.retry else None
        if plan.retry and plan.retry_at is not None:
            reason = (
                f"{failure.message} Trying again automatically at "
                f"{plan.retry_at:%H:%M} UTC (run {attempt + 1} of {most})."
            )
        else:
            runs = f" after {attempt} runs" if 1 < attempt <= most else ""
            reason = f"{failure.message} Stopped{runs}. {failure.advice}"

        await self.session.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(
                status=SubmissionStatus.FAILED,
                error=reason,
                retry_at=plan.retry_at,
                retry_token=token,
            )
        )
        failed = await self.session.get(Submission, submission_id, populate_existing=True)
        if failed is not None:
            set_state(self.session, failed, SubmissionState.FAILED, reason=reason)
            record_step(
                self.session,
                submission_id=submission_id,
                step=StepName.PIPELINE,
                result=StepResult.ERROR,
                message=reason,
                input={"run": attempt, "max_runs": most},
                output={
                    "temporary": failure.temporary,
                    "retry_at": plan.retry_at.isoformat() if plan.retry_at else None,
                },
                error_details=technical_details(exc),
            )
        if reprocess_run_id is not None and not plan.retry:  # a retry keeps the run open
            await finish_run(self.session, reprocess_run_id, error=reason)
        await self.session.commit()

        if token is not None:
            logger.warning(
                "Submission %s failed (run %d of %d), retry in %ds: %s",
                submission_id,
                attempt,
                most,
                plan.delay_seconds,
                technical_details(exc, limit=300),
            )
            return RetryLater(token, plan.delay_seconds)
        logger.exception("Submission %s failed (run %d of %d)", submission_id, attempt, most)
        return None

    async def _finish(self, submission: Submission) -> None:
        submission.status = SubmissionStatus.PROCESSED
        submission.processed_at = datetime.now(UTC)
        statuses = (
            await self.session.scalars(
                select(Timesheet.status).where(Timesheet.submission_id == submission.id)
            )
        ).all()
        state = state_from_timesheets(statuses)
        if state is not None:
            set_state(self.session, submission, state)
            return
        failed = [d for d in submission.documents if d.status == DocumentStatus.FAILED]
        if failed:
            set_state(self.session, submission, SubmissionState.FAILED, reason=failed[0].error)
        else:
            set_state(
                self.session,
                submission,
                SubmissionState.IGNORED,
                reason="No timesheet found in this email or upload.",
            )

    async def _read(self, document: Document) -> None:
        watch = Stopwatch()
        step_input = {"file": document.filename, "size_bytes": document.size_bytes}
        data = await upload_buffer.get_file(document.id)
        if data is None:
            document.status = DocumentStatus.FAILED
            document.error = "The file expired before it was processed. Upload it again."
            record_step(
                self.session,
                submission_id=document.submission_id,
                document_id=document.id,
                step=StepName.READ,
                result=StepResult.ERROR,
                message=document.error,
                input=step_input,
                duration_ms=watch.ms,
            )
            return
        try:
            # Docling is CPU-heavy and blocking: run it off the event loop.
            text = await asyncio.to_thread(read_document, document.filename, data)
        except DocumentReadError as exc:
            document.status = DocumentStatus.FAILED
            document.error = friendly_read_error(document.filename, exc)
            record_step(
                self.session,
                submission_id=document.submission_id,
                document_id=document.id,
                step=StepName.READ,
                result=StepResult.ERROR,
                message=document.error,
                input=step_input,
                error_details=repr(exc),
                duration_ms=watch.ms,
            )
            logger.warning("Could not read %s: %s", document.filename, exc)
            return
        document.extracted_text = text = db_safe(text)  # a NUL would make the save fail
        document.status = DocumentStatus.PARSED
        document.error = None
        record_step(
            self.session,
            submission_id=document.submission_id,
            document_id=document.id,
            step=StepName.READ,
            result=StepResult.SUCCESS,
            message=f"Read {document.filename}",
            input=step_input,
            output={"characters": len(text)},
            duration_ms=watch.ms,
        )
        logger.info("Read %s: %d characters", document.filename, len(text))

    async def _has_timesheets(self, document_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Timesheet.id)
            .where(
                Timesheet.document_id == document_id,
                Timesheet.status != TimesheetStatus.SUPERSEDED,
            )
            .limit(1)
        )
        return found is not None

    async def _extract(
        self, submission: Submission, document: Document, company: Company | None
    ) -> None:
        set_state(self.session, submission, SubmissionState.MATCHING)
        watch = Stopwatch()
        step_input = {
            "file": document.filename,
            "characters": len(document.extracted_text or ""),
            "truncated": len(document.extracted_text or "") > settings.llm_max_input_chars,
        }
        try:
            with pipeline_span(
                "ai.extract",
                characters=step_input["characters"],
                truncated=step_input["truncated"],
                model=settings.llm_model,
            ) as span:
                result = await extract_timesheets(
                    document_text=document.extracted_text or "",
                    filename=document.filename,
                    received_at=submission.received_at,
                    email_subject=submission.subject,
                    email_body=submission.body_text,
                )
                span.set_attribute("timesheets", len(result.timesheets))
        except Exception as exc:
            # Usually temporary (model down, timeout): log the step, then let the whole
            # submission fail so it can be retried or reprocessed.
            record_step(
                self.session,
                submission_id=submission.id,
                document_id=document.id,
                step=StepName.EXTRACT,
                result=StepResult.ERROR,
                message=f"Could not extract timesheet details from {document.filename}: "
                "the AI model did not answer or returned invalid data.",
                input=step_input,
                error_details=repr(exc),
                duration_ms=watch.ms,
            )
            await self.session.commit()
            raise

        if not result.timesheets:
            document.error = "No timesheet found in this document."
            record_step(
                self.session,
                submission_id=submission.id,
                document_id=document.id,
                step=StepName.EXTRACT,
                result=StepResult.WARNING,
                message=f"{document.filename} is not a timesheet",
                input=step_input,
                output={"timesheets": 0},
                duration_ms=watch.ms,
            )
            return
        record_step(
            self.session,
            submission_id=submission.id,
            document_id=document.id,
            step=StepName.EXTRACT,
            result=StepResult.SUCCESS,
            message=f"Found {len(result.timesheets)} timesheet(s) in {document.filename}",
            input=step_input,
            output={
                "timesheets": [
                    {
                        "employee_name": t.employee_name,
                        "employee_code": t.employee_code,
                        "days": len(t.days),
                        "stated_total": t.stated_total,
                        "confidence": t.confidence,
                    }
                    for t in result.timesheets
                ]
            },
            duration_ms=watch.ms,
        )

        companies = await self._company_records()
        sender = companies.get(submission.company_id) if submission.company_id else None
        is_email_body = document.filename == BODY_FILENAME
        truncated_flag = truncation_flag(document.extracted_text or "")

        # 1. Which company and which employee is each timesheet for?
        built: list[tuple[Timesheet, _CompanyContext]] = []
        version = await next_version(self.session, document.id)  # 2+ after a reprocess
        for extracted in result.timesheets:
            watch = Stopwatch()
            decision = decide_company(extracted.company_name, sender, list(companies.values()))
            cc = await self._company_context(decision.company_id)
            ctx = BuildContext(
                submission_id=submission.id,
                document_id=document.id,
                company_id=decision.company_id,
                received_on=submission.received_at.date(),
                week_start_day=cc.company.week_start if cc.company else 0,
                is_email_body=is_email_body,
            )
            for timesheet in build_timesheets(extracted, ctx):  # one per week
                match_started = now_ns()
                extra = [f for f in (decision.flag, truncated_flag) if f is not None]
                if extra:
                    timesheet.flags = [*timesheet.flags, *extra]
                timesheet.version = version
                timesheet.reprocess_run_id = current_reprocess_run.get()
                match = (
                    match_employee(timesheet.extracted_name, timesheet.extracted_code, cc.records)
                    if cc.company
                    else MatchResult(None, None)
                )
                employee = cc.by_id.get(match.employee_id) if match.employee_id else None
                apply_match(
                    timesheet, match, company_known=cc.company is not None, matched=employee
                )
                self.session.add(timesheet)
                await self.session.flush()  # the timesheet id is known now
                finished_span(
                    "timesheet.match",
                    match_started,
                    timesheet_id=timesheet.id,
                    method=match.method,
                    matched=employee is not None,
                    confidence=float(timesheet.confidence or 0),
                )
                record_step(
                    self.session,
                    submission_id=submission.id,
                    document_id=document.id,
                    timesheet_id=timesheet.id,
                    step=StepName.MATCH,
                    result=StepResult.SUCCESS if employee else StepResult.WARNING,
                    message=timesheet.match_reason or "",
                    input={
                        "name": timesheet.extracted_name,
                        "code": timesheet.extracted_code,
                        "company_written": timesheet.extracted_company_name,
                        "sender_company": sender.name if sender else None,
                    },
                    output={
                        "company": cc.company.name if cc.company else None,
                        "employee_id": str(employee.id) if employee else None,
                        "employee": employee.full_name if employee else None,
                        "method": match.method,
                        "confidence": float(timesheet.confidence or 0),
                        "candidates": [
                            {"name": c.full_name, "code": c.code, "score": round(c.score, 2)}
                            for c in match.candidates
                        ],
                    },
                    duration_ms=watch.ms,
                )
                built.append((timesheet, cc))

        # 2. Pay rules, assignment dates, duplicates, decision
        set_state(self.session, submission, SubmissionState.RULE_CHECKS)
        # Hold (employee, week) locks until this document is committed, so two workers
        # handling the same resent email cannot both miss each other's timesheet.
        await lock_employee_weeks(self.session, [(t.employee_id, t.week_start) for t, _ in built])
        for timesheet, cc in built:
            watch = Stopwatch()
            rules_started = now_ns()
            recalculate(timesheet, cc.rules, cc.holidays, default_rules_used=cc.company is None)
            placed = cc.employees.get(timesheet.employee_id) if timesheet.employee_id else None
            if placed is not None:
                check_assignment(timesheet, placed.assignment_start, placed.assignment_end)
            await validate_duplicates(self.session, timesheet, document)
            codes = [f.get("code") for f in timesheet.flags or []]
            finished_span(
                "timesheet.rules",
                rules_started,
                timesheet_id=timesheet.id,
                flags=len(codes),
                flag_codes=",".join(str(c) for c in codes),  # codes only, no messages
                severity=timesheet.severity,
                days=len(timesheet.entries),
            )
            record_step(
                self.session,
                submission_id=submission.id,
                document_id=document.id,
                timesheet_id=timesheet.id,
                step=StepName.RULES,
                result=StepResult.WARNING if codes else StepResult.SUCCESS,
                message=f"{len(codes)} flag(s): {', '.join(str(c) for c in codes)}"
                if codes
                else "All rule checks passed",
                input={"days": len(timesheet.entries)},
                output={
                    "regular": float(timesheet.regular_hours),
                    "overtime": float(timesheet.overtime_hours),
                    "double_time": float(timesheet.double_time_hours),
                    "holiday": float(timesheet.holiday_hours),
                    "gross_amount": _gross(timesheet),
                    "flags": timesheet.flags,
                },
                duration_ms=watch.ms,
            )

            decide_started = now_ns()
            if can_auto_approve(timesheet):
                timesheet.status = TimesheetStatus.APPROVED
                timesheet.reviewed_at = datetime.now(UTC)
                action, why = "auto_approved", "Matched, confident and no blocking flags"
            else:
                timesheet.status = TimesheetStatus.NEEDS_REVIEW
                action, why = "sent_to_review", "Needs a reviewer"
            record_step(
                self.session,
                submission_id=submission.id,
                document_id=document.id,
                timesheet_id=timesheet.id,
                step=StepName.DECIDE,
                result=StepResult.SUCCESS,
                message=f"{'Approved automatically' if action == 'auto_approved' else why}",
                input={
                    "confidence": float(timesheet.confidence or 0),
                    "severity": timesheet.severity,
                },
                output={"status": timesheet.status, "reason": why},
            )
            finished_span(
                "timesheet.decide",
                decide_started,
                timesheet_id=timesheet.id,
                status=timesheet.status,
                auto_approved=action == "auto_approved",
            )
            record_event(
                self.session,
                entity_type="timesheet",
                entity_id=timesheet.id,
                action=action,
                details={
                    "match_method": timesheet.match_method,
                    "confidence": float(timesheet.confidence or 0),
                    "flags": codes,
                },
            )
            logger.info(
                "Timesheet %s for %s: %s (flags: %s)",
                timesheet.id,
                timesheet.extracted_name or "?",
                timesheet.status,
                ", ".join(str(c) for c in codes) or "none",
            )

        logger.info("Extracted %d timesheet(s) from %s", len(result.timesheets), document.filename)


async def process_submission_by_id(
    submission_id: uuid.UUID,
    *,
    reprocess_run_id: uuid.UUID | None = None,
    retry_token: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        await ProcessingService(session).process(submission_id, reprocess_run_id, retry_token)
