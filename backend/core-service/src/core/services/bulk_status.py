"""Activate / deactivate many employees, companies or holidays at once, and delete many
holidays (admin only, at most one page = 100 at a time).

Each item goes through the same rules as a single change and is committed on its own,
so one bad item is reported and the others still go through. An item that already has
the requested status counts as done (nothing changes). Every change writes an audit
event (activated / deactivated / deleted, with bulk=true).

Deactivating a company also deactivates its employees (CompanyService); activating a
company does not reactivate them (some may have been inactive before)."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, NotFoundError, ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.audit import record_event
from src.core.services.company_service import CompanyService
from src.data.models import Company, Employee, Holiday
from src.data.repositories.holiday_repository import HolidayRepository
from src.schemas.bulk import BulkDeleteResult, BulkStatusItem, BulkStatusResult

Entity = Literal["employee", "company", "holiday"]


def _action(is_active: bool) -> str:
    return "activated" if is_active else "deactivated"


class BulkStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _each(
        self,
        ids: list[uuid.UUID],
        change: Callable[[uuid.UUID], Awaitable[BulkStatusItem]],
    ) -> list[BulkStatusItem]:
        results: list[BulkStatusItem] = []
        for item_id in ids:
            try:
                results.append(await change(item_id))
                await self.session.commit()
            except AppError as exc:
                await self.session.rollback()  # drop anything half-done for this item
                results.append(BulkStatusItem(id=item_id, ok=False, error=exc.message))
        return results

    @staticmethod
    def _summary(results: list[BulkStatusItem], **extra: int) -> BulkStatusResult:
        succeeded = sum(1 for r in results if r.ok)
        return BulkStatusResult(
            requested=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
            **extra,
        )

    def _audit(
        self,
        entity: Entity,
        entity_id: uuid.UUID,
        action: str,
        actor: Principal,
        **details: object,
    ) -> None:
        record_event(
            self.session,
            entity_type=entity,
            entity_id=entity_id,
            action=action,
            actor=actor,
            details={"bulk": True, **details},
        )

    # --- employees
    # ---------------------------------------------------------------------

    async def employees(
        self, ids: list[uuid.UUID], is_active: bool, actor: Principal
    ) -> BulkStatusResult:
        async def change(employee_id: uuid.UUID) -> BulkStatusItem:
            employee = await self.session.get(Employee, employee_id)
            if employee is None:
                raise NotFoundError("Employee not found.")
            if employee.is_active == is_active:
                return BulkStatusItem(id=employee_id, ok=True, is_active=is_active)
            if is_active:
                company = await self.session.get(Company, employee.company_id)
                if company is not None and not company.is_active:
                    raise ValidationFailedError(
                        f"{employee.full_name}: the company {company.name} is "
                        "inactive. Activate the company first."
                    )
            employee.is_active = is_active
            self._audit("employee", employee.id, _action(is_active), actor)
            return BulkStatusItem(
                id=employee_id, ok=True, changed=True, is_active=is_active
            )

        return self._summary(await self._each(ids, change))

    # --- companies
    # ---------------------------------------------------------------------

    async def companies(
        self, ids: list[uuid.UUID], is_active: bool, actor: Principal
    ) -> BulkStatusResult:
        cascaded = 0

        async def change(company_id: uuid.UUID) -> BulkStatusItem:
            nonlocal cascaded
            company = await self.session.get(Company, company_id)
            if company is None:
                raise NotFoundError("Company not found.")
            if company.is_active == is_active:
                return BulkStatusItem(id=company_id, ok=True, is_active=is_active)
            employees: Sequence[uuid.UUID] = []
            if not is_active:
                employees = await CompanyService(self.session).deactivate_employees(
                    company.id
                )
                for employee_id in employees:
                    self._audit(
                        "employee",
                        employee_id,
                        "deactivated",
                        actor,
                        reason="company deactivated",
                        company_id=str(company.id),
                    )
            company.is_active = is_active
            self._audit(
                "company",
                company.id,
                _action(is_active),
                actor,
                employees_deactivated=len(employees),
            )
            cascaded += len(employees)
            return BulkStatusItem(
                id=company_id, ok=True, changed=True, is_active=is_active
            )

        results = await self._each(ids, change)
        return self._summary(results, employees_deactivated=cascaded)

    # --- holidays
    # ----------------------------------------------------------------------

    async def holidays(
        self, ids: list[uuid.UUID], is_active: bool, actor: Principal
    ) -> BulkStatusResult:
        async def change(holiday_id: uuid.UUID) -> BulkStatusItem:
            holiday = await self.session.get(Holiday, holiday_id)
            if holiday is None:
                raise NotFoundError("Holiday not found.")
            if holiday.is_active == is_active:
                return BulkStatusItem(id=holiday_id, ok=True, is_active=is_active)
            holiday.is_active = is_active
            self._audit(
                "holiday",
                holiday.id,
                _action(is_active),
                actor,
                date=holiday.holiday_date.isoformat(),
                name=holiday.name,
            )
            return BulkStatusItem(
                id=holiday_id, ok=True, changed=True, is_active=is_active
            )

        return self._summary(await self._each(ids, change))

    async def delete_holidays(
        self, ids: list[uuid.UUID], actor: Principal
    ) -> BulkDeleteResult:
        repository = HolidayRepository(self.session)

        async def remove(holiday_id: uuid.UUID) -> BulkStatusItem:
            holiday = await self.session.get(Holiday, holiday_id)
            if holiday is None:
                raise NotFoundError("Holiday not found.")
            self._audit(
                "holiday",
                holiday.id,
                "deleted",
                actor,
                date=holiday.holiday_date.isoformat(),
                name=holiday.name,
                company_id=str(holiday.company_id) if holiday.company_id else None,
            )
            await repository.delete(holiday)
            return BulkStatusItem(id=holiday_id, ok=True, changed=True)

        results = await self._each(ids, remove)
        deleted = sum(1 for r in results if r.ok)
        return BulkDeleteResult(
            requested=len(results),
            deleted=deleted,
            failed=len(results) - deleted,
            results=results,
        )
