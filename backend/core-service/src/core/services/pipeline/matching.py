"""Which company and which employee is each extracted timesheet for?"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import StepName, StepResult
from src.core.services.activity_log import Stopwatch, current_reprocess_run, record_step
from src.core.services.company_matcher import CompanyRecord, decide_company
from src.core.services.email_intake_service import BODY_FILENAME
from src.core.services.employee_matcher import (
    EmployeeRecord,
    MatchResult,
    apply_match,
    match_employee,
    to_record,
)
from src.core.services.pay_rules import PayRules, rules_from_company
from src.core.services.pipeline.extracting import Extraction
from src.core.services.reprocess import next_version
from src.core.services.timesheet_builder import BuildContext, build_timesheets, truncation_flag
from src.data.clients.document_limits import too_large_flag
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.data.repositories.employee_repository import EmployeeRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.observability.tracing.spans import finished_span, now_ns


@dataclass(slots=True)
class CompanyContext:
    """Everything the rules need for one company, loaded once per document."""

    company: Company | None
    rules: PayRules
    holidays: set[date]
    records: list[EmployeeRecord]  # for matching
    by_id: dict[uuid.UUID, EmployeeRecord]
    employees: dict[uuid.UUID, Employee]  # for assignment dates


class CompanyContexts:
    """Company contexts loaded on first use and kept for the rest of the job."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._contexts: dict[uuid.UUID | None, CompanyContext] = {}

    async def company_records(self) -> dict[uuid.UUID, CompanyRecord]:
        rows = await self.session.scalars(select(Company).where(Company.is_active.is_(True)))
        return {c.id: CompanyRecord(c.id, c.name, tuple(c.aliases or ())) for c in rows.all()}

    async def get(self, company_id: uuid.UUID | None) -> CompanyContext:
        if company_id not in self._contexts:
            company = await self.session.get(Company, company_id) if company_id else None
            active = (
                await EmployeeRepository(self.session).list_active(company.id) if company else []
            )
            records = [to_record(e) for e in active]
            self._contexts[company_id] = CompanyContext(
                company=company,
                rules=rules_from_company(company),
                holidays=set(await HolidayRepository(self.session).dates_for(company_id)),
                records=records,
                by_id={r.id: r for r in records},
                employees={e.id: e for e in active},
            )
        return self._contexts[company_id]


async def match_timesheets(
    session: AsyncSession,
    contexts: CompanyContexts,
    submission: Submission,
    document: Document,
    extraction: Extraction,
) -> list[tuple[Timesheet, CompanyContext]]:
    """One Timesheet row per person and week, with its company and employee decided,
    added to the session and written to the step log."""
    companies = await contexts.company_records()
    sender = companies.get(submission.company_id) if submission.company_id else None
    is_email_body = document.filename == BODY_FILENAME
    truncated_flag = truncation_flag(extraction.text) if extraction.truncated else None
    size_flag = too_large_flag(document.read_limit)  # pages / sheets not read

    built: list[tuple[Timesheet, CompanyContext]] = []
    version = await next_version(session, document.id)  # 2+ after a reprocess
    for extracted in extraction.result.timesheets:
        watch = Stopwatch()
        decision = decide_company(extracted.company_name, sender, list(companies.values()))
        cc = await contexts.get(decision.company_id)
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
            extra = [
                f
                for f in (decision.flag, truncated_flag, size_flag, extraction.missing_flag)
                if f is not None
            ]
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
            apply_match(timesheet, match, company_known=cc.company is not None, matched=employee)
            session.add(timesheet)
            await session.flush()  # the timesheet id is known now
            finished_span(
                "timesheet.match",
                match_started,
                timesheet_id=timesheet.id,
                method=match.method,
                matched=employee is not None,
                confidence=float(timesheet.confidence or 0),
            )
            record_step(
                session,
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
    return built
