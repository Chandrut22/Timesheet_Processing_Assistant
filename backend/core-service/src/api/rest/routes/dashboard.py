"""The dashboard numbers: GET /dashboard (the live stream is in routes/sse.py)."""

from fastapi import APIRouter

from src.api.rest.dependencies import Reviewer, SessionDep
from src.core.services.dashboard_service import build_snapshot
from src.schemas.dashboard import DashboardSnapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(session: SessionDep, _: Reviewer) -> DashboardSnapshot:
    """The same snapshot the stream pushes. Used on first load and while the stream is
    down."""
    return await build_snapshot(session)
