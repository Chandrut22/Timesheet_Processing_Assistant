"""The email listener seen from the dashboard: its status and "Check mail now"."""

from fastapi import APIRouter
from fastapi import status as http_status

from src.api.rest.dependencies import Reviewer, SessionDep
from src.core.services.mailbox_service import MailboxService
from src.data.clients.redis import redis_client
from src.schemas.email import MailboxCheck, MailboxStatus

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/status")
async def mailbox_status(session: SessionDep, _: Reviewer) -> MailboxStatus:
    """Is the listener running, when did it last check, and what did it find."""
    return await MailboxService(session, redis_client).status()


@router.post("/check-now", status_code=http_status.HTTP_202_ACCEPTED)
async def check_now(session: SessionDep, actor: Reviewer) -> MailboxCheck:
    """Ask the listener to read the mailbox now. 202: queued; poll GET
    /email/check-now/{id}. 409 when reading email is turned off, 503 when the listener
    is not running, 429 within EMAIL_MANUAL_CHECK_COOLDOWN_SECONDS of the last request
    (Retry-After)."""
    return await MailboxService(session, redis_client).request_check(actor)


@router.get("/check-now/{request_id}")
async def check_result(
    request_id: str, session: SessionDep, _: Reviewer
) -> MailboxCheck:
    """queued, running, done (with counts) or failed (with the reason). Kept 10
    minutes."""
    return await MailboxService(session, redis_client).check(request_id)
