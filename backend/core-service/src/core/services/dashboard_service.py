from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.timesheet_status import SubmissionStatus, TimesheetStatus
from src.data.models.postgres.submission import Submission
from src.data.models.postgres.timesheet import Timesheet
from src.data.repositories.submission_repository import SubmissionRepository
from src.schemas.dashboard import DashboardCounts, DashboardSnapshot
from src.schemas.submission import SubmissionRead

RECENT = 10


async def build_snapshot(session: AsyncSession) -> DashboardSnapshot:
    """Everything the dashboard shows, in three queries."""
    needs_review, high, approved = (
        await session.execute(
            select(
                func.count().filter(Timesheet.status == TimesheetStatus.NEEDS_REVIEW),
                func.count().filter(
                    Timesheet.status == TimesheetStatus.NEEDS_REVIEW,
                    Timesheet.severity == "high",
                ),
                func.count().filter(Timesheet.status == TimesheetStatus.APPROVED),
            ).select_from(Timesheet)
        )
    ).one()
    failed = await session.scalar(
        select(func.count())
        .select_from(Submission)
        .where(Submission.status == SubmissionStatus.FAILED)
    )
    items, _ = await SubmissionRepository(session).search(
        status=None, state=None, source=None, company_id=None, page=1, size=RECENT
    )
    return DashboardSnapshot(
        counts=DashboardCounts(
            needs_review=needs_review,
            high_severity=high,
            approved_waiting_export=approved,
            failed_submissions=failed or 0,
        ),
        recent=[SubmissionRead.model_validate(s) for s in items],
    )
