import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from src.api.rest.dependencies import Reviewer, SessionDep
from src.core.services.upload_service import UploadService
from src.schemas.submission import SubmissionRead

router = APIRouter(tags=["uploads"])


@router.post("/uploads", status_code=status.HTTP_202_ACCEPTED)
async def upload_timesheets(
    session: SessionDep,
    principal: Reviewer,
    files: Annotated[list[UploadFile], File(description="PDF, DOCX, XLSX or images")],
    company_id: Annotated[uuid.UUID | None, Form()] = None,
) -> SubmissionRead:
    """202 Accepted: the files are saved and queued; processing happens in the
    background."""
    submission = await UploadService(session).create(files, company_id, principal)
    return SubmissionRead.model_validate(submission)
