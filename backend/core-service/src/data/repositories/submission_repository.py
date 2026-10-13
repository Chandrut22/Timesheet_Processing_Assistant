import uuid
from collections.abc import Sequence

from sqlalchemy import select

from src.data.models import Submission
from src.data.repositories.base import BaseRepository


class SubmissionRepository(BaseRepository[Submission]):
    model = Submission

    async def search(
        self,
        *,
        status: str | None,
        source: str | None,
        company_id: uuid.UUID | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[Submission], int]:
        query = select(Submission)
        if status:
            query = query.where(Submission.status == status)
        if source:
            query = query.where(Submission.source == source)
        if company_id is not None:
            query = query.where(Submission.company_id == company_id)
        return await self.paginate(
            query.order_by(Submission.received_at.desc(), Submission.id), page=page, size=size
        )
