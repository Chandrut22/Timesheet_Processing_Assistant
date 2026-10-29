import uuid
from collections.abc import Sequence

from sqlalchemy import and_, func, or_, select

from src.data.models import Company, WhitelistSender
from src.data.repositories.base import BaseRepository
from src.utils.senders import SenderKind


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def get_by_name(self, name: str) -> Company | None:
        return await self.session.scalar(
            select(Company).where(func.lower(Company.name) == name.strip().lower())
        )

    async def search(
        self, *, q: str | None, is_active: bool | None, page: int, size: int
    ) -> tuple[Sequence[Company], int]:
        query = select(Company)
        if q:
            query = query.where(Company.name.ilike(f"%{q.strip()}%"))
        if is_active is not None:
            query = query.where(Company.is_active.is_(is_active))
        return await self.paginate(
            query.order_by(Company.name, Company.id), page=page, size=size
        )


class WhitelistRepository(BaseRepository[WhitelistSender]):
    model = WhitelistSender

    async def list_for_company(
        self, company_id: uuid.UUID
    ) -> Sequence[WhitelistSender]:
        rows = await self.session.scalars(
            select(WhitelistSender)
            .where(WhitelistSender.company_id == company_id)
            .order_by(WhitelistSender.kind, WhitelistSender.value)
        )
        return rows.all()

    async def get_by_value(self, value: str) -> WhitelistSender | None:
        return await self.session.scalar(
            select(WhitelistSender).where(WhitelistSender.value == value)
        )

    async def find_company_id_for_sender(self, sender_email: str) -> uuid.UUID | None:
        """Which active company may this sender send for? An exact email beats a domain.
        (Used by the email listener next week.)"""
        email = sender_email.strip().lower()
        domain = email.rpartition("@")[2]
        return await self.session.scalar(
            select(WhitelistSender.company_id)
            .join(Company, Company.id == WhitelistSender.company_id)
            .where(
                Company.is_active.is_(True),
                or_(
                    and_(
                        WhitelistSender.kind == SenderKind.EMAIL,
                        WhitelistSender.value == email,
                    ),
                    and_(
                        WhitelistSender.kind == SenderKind.DOMAIN,
                        WhitelistSender.value == domain,
                    ),
                ),
            )
            .order_by((WhitelistSender.kind == SenderKind.EMAIL).desc())
            .limit(1)
        )
