import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from src.data.models import Employee
from src.data.repositories.base import BaseRepository


class EmployeeRepository(BaseRepository[Employee]):
    model = Employee

    async def get_by_code(self, company_id: uuid.UUID, code: str) -> Employee | None:
        return await self.session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                func.lower(Employee.employee_code) == code.strip().lower(),
            )
        )

    async def get_by_email(self, company_id: uuid.UUID, email: str) -> Employee | None:
        return await self.session.scalar(
            select(Employee).where(
                Employee.company_id == company_id, Employee.email == email.strip().lower()
            )
        )

    async def search(
        self,
        *,
        company_id: uuid.UUID | None,
        q: str | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[Employee], int]:
        query = select(Employee)
        if company_id is not None:
            query = query.where(Employee.company_id == company_id)
        if is_active is not None:
            query = query.where(Employee.is_active.is_(is_active))
        if q:
            pattern = f"%{q.strip()}%"
            query = query.where(
                or_(
                    Employee.full_name.ilike(pattern),
                    Employee.employee_code.ilike(pattern),
                    Employee.email.ilike(pattern),
                    func.array_to_string(Employee.aliases, " ").ilike(pattern),
                )
            )
        return await self.paginate(
            query.order_by(Employee.full_name, Employee.id), page=page, size=size
        )

    async def list_active(self, company_id: uuid.UUID) -> Sequence[Employee]:
        """Everyone matching may pick from: the company's active employees."""
        rows = await self.session.scalars(
            select(Employee).where(Employee.company_id == company_id, Employee.is_active.is_(True))
        )
        return rows.all()
