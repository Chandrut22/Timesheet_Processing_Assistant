from pydantic import BaseModel

from src.schemas.submission import SubmissionRead


class DashboardCounts(BaseModel):
    needs_review: int
    high_severity: int
    approved_waiting_export: int
    failed_submissions: int


class DashboardSnapshot(BaseModel):
    counts: DashboardCounts
    recent: list[SubmissionRead]  # the 10 newest submissions