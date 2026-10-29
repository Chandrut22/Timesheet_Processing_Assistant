"""Pay rules, assignment dates and duplicates for each timesheet, then the decision:
approved automatically, or sent to a reviewer."""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import StepName, StepResult, TimesheetStatus
from src.core.services.activity_log import Stopwatch, record_step
from src.core.services.audit import record_event
from src.core.services.pay_rules import recalculate
from src.core.services.pipeline.matching import CompanyContext
from src.core.services.timesheet_validation import (
    can_auto_approve,
    check_assignment,
    lock_employee_weeks,
    validate_duplicates,
)
from src.data.models import Document, Submission, Timesheet
from src.observability.tracing.spans import finished_span, now_ns

logger = logging.getLogger(__name__)


def gross(timesheet: Timesheet) -> float | None:
    parts = (
        timesheet.regular_amount,
        timesheet.overtime_amount,
        timesheet.double_time_amount,
        timesheet.holiday_amount,
    )
    if any(p is None for p in parts):
        return None
    return float(sum(p for p in parts if p is not None))


async def check_and_decide(
    session: AsyncSession,
    submission: Submission,
    document: Document,
    built: list[tuple[Timesheet, CompanyContext]],
) -> None:
    # Hold (employee, week) locks until this document is committed, so two workers
    # handling the same resent email cannot both miss each other's timesheet.
    await lock_employee_weeks(
        session, [(t.employee_id, t.week_start) for t, _ in built]
    )
    for timesheet, cc in built:
        watch = Stopwatch()
        rules_started = now_ns()
        recalculate(
            timesheet, cc.rules, cc.holidays, default_rules_used=cc.company is None
        )
        placed = (
            cc.employees.get(timesheet.employee_id) if timesheet.employee_id else None
        )
        if placed is not None:
            check_assignment(timesheet, placed.assignment_start, placed.assignment_end)
        await validate_duplicates(session, timesheet, document)
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
            session,
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
                "gross_amount": gross(timesheet),
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
            session,
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
            session,
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
