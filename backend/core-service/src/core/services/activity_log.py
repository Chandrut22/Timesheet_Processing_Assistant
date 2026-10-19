"""Write the email state log and the step-by-step log.

    set_state(...)       -> submissions.state + one submission_state_changes row
    record_step(...)     -> one processing_steps row (input, output, time, result)
    refresh_state(...)   -> the state that follows from the submission's timesheets

Nothing here commits: rows join the caller's transaction, so a log row is saved
exactly when the change it describes is saved."""

import time
import uuid
from collections.abc import Iterable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import StepName, StepResult, SubmissionState, TimesheetStatus
from src.core.rbac.principal import Principal
from src.data.models import ProcessingStep, Submission, SubmissionStateChange, Timesheet
from src.observability.tracing.spans import current_trace_id

MAX_DETAIL_CHARS = 2000

current_reprocess_run: ContextVar[uuid.UUID | None] = ContextVar(
    "current_reprocess_run", default=None
)


class Stopwatch:
    """`watch = Stopwatch()` ... `watch.ms` = milliseconds since it was made."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    @property
    def ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)


def set_state(
    session: AsyncSession,
    submission: Submission,
    state: SubmissionState,
    *,
    reason: str | None = None,
    actor: Principal | None = None,
    first: bool = False,
) -> None:
    """Move the submission to `state` and log the change (no row if nothing changed).
    The submission must already have its id (flush a new one first).
    first=True = the submission was just created: log "received" with no previous state."""
    if not first and submission.state == state and submission.state_reason == reason:
        return
    session.add(
        SubmissionStateChange(
            submission_id=submission.id,
            from_state=None if first else submission.state,
            to_state=state,
            reason=reason,
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else None,
            created_at=datetime.now(UTC),  # set here: the order rows were made in is the order
        )
    )
    submission.state = state
    submission.state_reason = reason


def record_step(
    session: AsyncSession,
    *,
    submission_id: uuid.UUID,
    step: StepName,
    result: StepResult,
    message: str,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    document_id: uuid.UUID | None = None,
    timesheet_id: uuid.UUID | None = None,
    duration_ms: int = 0,
    error_details: str | None = None,
) -> None:
    session.add(
        ProcessingStep(
            submission_id=submission_id,
            document_id=document_id,
            timesheet_id=timesheet_id,
            reprocess_run_id=current_reprocess_run.get(),
            step=step,
            result=result,
            message=message[:MAX_DETAIL_CHARS],
            input=input or {},
            output=output or {},
            error_details=error_details[:MAX_DETAIL_CHARS] if error_details else None,
            duration_ms=duration_ms,
            trace_id=current_trace_id(),
            created_at=datetime.now(UTC),
        )
    )


def state_from_timesheets(statuses: Iterable[str]) -> SubmissionState | None:
    """Pure: the state a set of timesheets adds up to. None = no timesheets.

    any waiting for a reviewer -> awaiting_review; all exported -> exported;
    any approved (or exported) -> approved; otherwise all rejected -> rejected.
    Superseded timesheets (replaced by a reprocess) do not count."""
    found = set(statuses) - {TimesheetStatus.SUPERSEDED}
    if not found:
        return None
    if TimesheetStatus.NEEDS_REVIEW in found:
        return SubmissionState.AWAITING_REVIEW
    if found == {TimesheetStatus.EXPORTED}:
        return SubmissionState.EXPORTED
    if found & {TimesheetStatus.APPROVED, TimesheetStatus.EXPORTED}:
        return SubmissionState.APPROVED
    return SubmissionState.REJECTED


async def refresh_state(
    session: AsyncSession, submission_id: uuid.UUID, *, actor: Principal | None = None
) -> None:
    """After a review or an export: move the submission to the state its timesheets show."""
    submission = await session.get(Submission, submission_id)
    if submission is None:
        return
    await session.flush()
    statuses = (
        await session.scalars(
            select(Timesheet.status).where(Timesheet.submission_id == submission_id)
        )
    ).all()
    state = state_from_timesheets(statuses)
    if state is not None:
        set_state(session, submission, state, actor=actor)
