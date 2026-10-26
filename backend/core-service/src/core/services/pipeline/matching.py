"""Which company and which employee is each extracted timesheet for?"""

import uuid
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import StepName, StepResult
from src.core.services.activity_log import Stopwatch, current_reprocess_run, record_step
from src.core.services.chunking import Combined, combine_by
from src.core.services.company_matcher import CompanyDecision, CompanyRecord, decide_company
from src.core.services.documents.document_limits import too_large_flag
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
from src.core.services.reprocess import adopt, pick_predecessor, previous_timesheets, retire
from src.core.services.timesheet_builder import BuildContext, build_timesheets
from src.data.models import Company, Document, Employee, ReprocessRun, Submission, Timesheet
from src.data.repositories.employee_repository import EmployeeRepository
from src.data.repositories.holiday_repository import HolidayRepository
from src.observability.tracing.spans import finished_span, now_ns
from src.schemas.extraction import ExtractedTimesheet


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
    added to the session and written to the step log.

    In a reprocess, a newly extracted timesheet updates the document's existing one for
    the same person / week (same id, version + 1, see reprocess.py); old ones that were
    not found again are rejected with the removed_by_reprocess flag."""
    companies = await contexts.company_records()
    sender = companies.get(submission.company_id) if submission.company_id else None
    is_email_body = document.filename == BODY_FILENAME
    size_flag = too_large_flag(document.read_limit)  # pages / sheets not read

    run_id = current_reprocess_run.get()
    run = await session.get(ReprocessRun, run_id) if run_id is not None else None
    olds = await previous_timesheets(session, document.id, run.id) if run is not None else []

    combined = extraction.combined
    if extraction.parts > 1:  # read in parts: join the same employee written differently
        combined = await _combine_after_matching(
            session, contexts, submission, document, combined, sender, companies
        )

    candidates: list[tuple[Timesheet, CompanyContext, CompanyDecision, list[dict[str, Any]]]] = []
    for extracted, part_flags in zip(combined.result.timesheets, combined.flags, strict=True):
        decision = decide_company(extracted.company_name, sender, list(companies.values()))
        cc = await contexts.get(decision.company_id)
        ctx = BuildContext(
            submission_id=submission.id,
            document_id=document.id,
            company_id=decision.company_id,
            received_on=submission.received_at.date(),
            week_start_day=cc.company.week_start if cc.company else 0,
            is_email_body=is_email_body,
            writing_class=document.writing_class,  # photos / scans read by the vision model
            has_handwritten_hours=document.has_handwritten_hours,
            unclear_marks=document.unclear_marks,
        )
        per_week = build_timesheets(extracted, ctx)
        candidates += [(t, cc, decision, part_flags) for t in per_week]

    built: list[tuple[Timesheet, CompanyContext]] = []
    for candidate, cc, decision, part_flags in candidates:
        watch = Stopwatch()
        match_started = now_ns()
        extra = [f for f in (decision.flag, size_flag, extraction.missing_flag) if f is not None]
        extra += extraction.size_flags  # long document: truncated / not read in full
        extra += part_flags  # read in parts: overlap disagreements
        if extra:
            candidate.flags = [*candidate.flags, *extra]
        timesheet = candidate
        if run is not None:
            old = pick_predecessor(candidate, olds, only_one_new=len(candidates) == 1)
            if old is not None:
                olds.remove(old)
                timesheet = await adopt(session, old, candidate, run)  # same row, new version
            else:
                timesheet.reprocess_run_id = run.id  # someone / a week new in this run
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
                "version": timesheet.version,
            },
            duration_ms=watch.ms,
        )
        built.append((timesheet, cc))

    if run is not None:
        for old in olds:  # not found again: rejected, flagged, kept
            retire(session, old, run)
        await session.flush()
    return built


def _week_key(extracted: ExtractedTimesheet) -> str:
    """The week a timesheet is for: its week start, else the Monday of its first date."""
    if extracted.week_start:
        return extracted.week_start.isoformat()
    dates = [d.work_date for d in extracted.days if d.work_date]
    if not dates:
        return ""
    first = min(dates)
    return (first - timedelta(days=first.weekday())).isoformat()


async def _combine_after_matching(
    session: AsyncSession,
    contexts: CompanyContexts,
    submission: Submission,
    document: Document,
    combined: Combined,
    sender: CompanyRecord | None,
    companies: dict[uuid.UUID, CompanyRecord],
) -> Combined:
    """A document read in parts: timesheets from DIFFERENT parts matched to the same
    employee and week ("R. Kumar" in part 2, "Rahul Kumar" in part 3) become one.
    Unmatched timesheets, and two from the same part, are never joined."""
    keys: list[Hashable | None] = []
    for extracted in combined.result.timesheets:
        decision = decide_company(extracted.company_name, sender, list(companies.values()))
        cc = await contexts.get(decision.company_id)
        match = (
            match_employee(extracted.employee_name, extracted.employee_code, cc.records)
            if cc.company
            else MatchResult(None, None)
        )
        keys.append(
            (decision.company_id, match.employee_id, _week_key(extracted))
            if match.employee_id
            else None
        )
    again = combine_by(combined, keys)
    joined = len(combined.result.timesheets) - len(again.result.timesheets)
    if joined:
        record_step(
            session,
            submission_id=submission.id,
            document_id=document.id,
            step=StepName.MATCH,
            result=StepResult.SUCCESS,
            message=f"{joined} timesheet(s) from different parts of {document.filename} "
            "were combined: the same employee and week, written differently.",
            output={
                "before": len(combined.result.timesheets),
                "after": len(again.result.timesheets),
                "timesheets": [
                    {
                        "employee_name": t.employee_name,
                        "employee_code": t.employee_code,
                        "parts": sorted(parts),
                    }
                    for t, parts in zip(again.result.timesheets, again.parts, strict=True)
                    if len(parts) > 1
                ],
            },
        )
    return again
