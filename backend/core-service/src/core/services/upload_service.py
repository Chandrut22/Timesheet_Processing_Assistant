import hashlib
import uuid
from collections.abc import Sequence
from pathlib import PurePath

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.file_types import SUPPORTED_EXTENSIONS, skip_reason
from src.constants.timesheet_status import (
    DocumentStatus,
    StepName,
    StepResult,
    SubmissionSource,
    SubmissionState,
    SubmissionStatus,
)
from src.control.workers.dispatch import enqueue_or_leave_for_sweeper
from src.core.exceptions import ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.activity_log import record_step, set_state
from src.data.clients import upload_buffer
from src.data.models import Document, Submission
from src.data.repositories.company_repository import CompanyRepository
from src.utils.text import db_safe


def _safe_filename(raw: str | None) -> str:
    name = PurePath(db_safe(raw or "file").replace("\\", "/")).name  # drop any path sent
    return name[:255] or "file"


class UploadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, files: Sequence[UploadFile], company_id: uuid.UUID | None, principal: Principal
    ) -> Submission:
        if not files:
            raise ValidationFailedError("Attach at least one file.")
        if len(files) > settings.max_files_per_upload:
            raise ValidationFailedError(
                f"At most {settings.max_files_per_upload} files per upload."
            )
        if company_id is not None:
            company = await CompanyRepository(self.session).get(company_id)
            if company is None or not company.is_active:
                raise ValidationFailedError("Company not found or inactive.")

        max_bytes = settings.max_upload_mb * 1024 * 1024
        submission = Submission(
            source=SubmissionSource.UPLOAD,
            status=SubmissionStatus.RECEIVED,
            company_id=company_id,
            uploaded_by_id=principal.id,  # cross-service reference: UUID + name, no FK
            uploaded_by_name=principal.name,
        )
        to_buffer: list[tuple[Document, bytes]] = []

        for upload in files:
            filename = _safe_filename(upload.filename)
            data = await upload.read(max_bytes + 1)  # never read more than the limit
            if len(data) > max_bytes:
                raise ValidationFailedError(
                    f"'{filename}' is larger than {settings.max_upload_mb} MB."
                )
            if not data:
                raise ValidationFailedError(f"'{filename}' is empty.")

            extension = PurePath(filename).suffix.lower()
            reason = skip_reason(extension, len(data))
            document = Document(
                filename=filename,
                content_type=SUPPORTED_EXTENSIONS.get(
                    extension, upload.content_type or "application/octet-stream"
                )[:100],
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                status=DocumentStatus.UNSUPPORTED if reason else DocumentStatus.PENDING,
                error=reason,
            )
            submission.documents.append(document)
            if reason is None:
                to_buffer.append((document, data))

        self.session.add(submission)
        await self.session.flush()  # ids are known now
        set_state(self.session, submission, SubmissionState.RECEIVED, actor=principal, first=True)
        skipped = [d for d in submission.documents if d.status == DocumentStatus.UNSUPPORTED]
        record_step(
            self.session,
            submission_id=submission.id,
            step=StepName.COLLECT,
            result=StepResult.WARNING if skipped else StepResult.SUCCESS,
            message=f"Uploaded {len(submission.documents)} file(s) by {principal.name}"
            + (f"; {len(skipped)} will not be read" if skipped else ""),
            input={"files": len(files), "company_id": str(company_id) if company_id else None},
            output={
                "documents": [
                    {"file": d.filename, "status": d.status, "reason": d.error}
                    for d in submission.documents
                ]
            },
        )
        for document, data in to_buffer:  # bytes go to Redis BEFORE the commit...
            await upload_buffer.put_file(document.id, data)
        await self.session.commit()  # ...so the worker never sees a row without its file
        await enqueue_or_leave_for_sweeper(submission.id)  # queue down: the sweeper queues it
        return submission
