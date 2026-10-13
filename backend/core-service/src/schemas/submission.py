import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    created_at: datetime


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    status: str
    company_id: uuid.UUID | None
    sender_email: str | None
    subject: str | None
    uploaded_by_id: uuid.UUID | None
    uploaded_by_name: str | None
    received_at: datetime
    processed_at: datetime | None
    error: str | None
    documents: list[DocumentRead]
