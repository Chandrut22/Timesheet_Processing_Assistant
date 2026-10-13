import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from src.data.models import Employee
from src.data.repositories.base import commit_or_conflict
from src.data.repositories.company_repository import CompanyRepository
from src.data.repositories.employee_repository import EmployeeRepository
from src.schemas.employee import EmployeeCreate, EmployeeUpdate

DUPLICATE = "An employee with this code or email already exists in this company."


class EmployeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.employees = EmployeeRepository(session)
        self.companies = CompanyRepository(session)

    async def get(self, employee_id: uuid.UUID) -> Employee:
        employee = await self.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("Employee not found.")
        return employee

    async def list(
        self,
        *,
        company_id: uuid.UUID | None,
        q: str | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> tuple[Sequence[Employee], int]:
        return await self.employees.search(
            company_id=company_id, q=q, is_active=is_active, page=page, size=size
        )

    async def create(self, data: EmployeeCreate) -> Employee:
        company = await self.companies.get(data.company_id)
        if company is None:
            raise ValidationFailedError("Company not found.")
        if not company.is_active:
            raise ValidationFailedError("Cannot add employees to an inactive company.")

        email = data.email.lower() if data.email else None
        await self._ensure_unique(data.company_id, data.employee_code, email)

        employee = await self.employees.add(
            Employee(
                company_id=data.company_id,
                employee_code=data.employee_code,
                full_name=data.full_name,
                email=email,
                aliases=data.aliases,
            )
        )
        await commit_or_conflict(self.session, DUPLICATE)
        await self.session.refresh(employee)
        return employee

    async def update(self, employee_id: uuid.UUID, data: EmployeeUpdate) -> Employee:
        employee = await self.get(employee_id)
        changes = data.model_dump(exclude_unset=True)

        code = changes.get("employee_code")
        code = " ".join(code.split()) if code else None
        email = changes["email"].lower() if changes.get("email") else None
        await self._ensure_unique(employee.company_id, code, email, exclude_id=employee.id)

        if code:
            employee.employee_code = code
        if changes.get("full_name"):
            employee.full_name = " ".join(changes["full_name"].split())
        if "email" in changes:  # null clears the email
            employee.email = email
        if changes.get("aliases") is not None:
            # Assign a new list: in-place changes to an ARRAY column are not tracked.
            employee.aliases = changes["aliases"]
        if changes.get("is_active") is not None:
            employee.is_active = changes["is_active"]

        await commit_or_conflict(self.session, DUPLICATE)
        await self.session.refresh(employee)
        return employee

    async def _ensure_unique(
        self,
        company_id: uuid.UUID,
        code: str | None,
        email: str | None,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if code:
            found = await self.employees.get_by_code(company_id, code)
            if found is not None and found.id != exclude_id:
                raise ConflictError(f"Employee code '{code}' is already used in this company.")
        if email:
            found = await self.employees.get_by_email(company_id, email)
            if found is not None and found.id != exclude_id:
                raise ConflictError(f"Email '{email}' is already used in this company.")
