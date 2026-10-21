import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.rest.dependencies import Admin, CurrentPrincipal, PaginationDep, SessionDep
from src.api.rest.routes.importing import add_import_routes
from src.core.services.employee_service import EmployeeService
from src.schemas.common import Page
from src.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("")
async def list_employees(
    session: SessionDep,
    _: CurrentPrincipal,
    paging: PaginationDep,
    company_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> Page[EmployeeRead]:
    items, total = await EmployeeService(session).list(
        company_id=company_id, q=q, is_active=is_active, page=paging.page, size=paging.size
    )
    return Page[EmployeeRead](
        items=[EmployeeRead.model_validate(e) for e in items],
        total=total,
        page=paging.page,
        size=paging.size,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employee(body: EmployeeCreate, session: SessionDep, _: Admin) -> EmployeeRead:
    return EmployeeRead.model_validate(await EmployeeService(session).create(body))


@router.get("/{employee_id}")
async def get_employee(
    employee_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> EmployeeRead:
    return EmployeeRead.model_validate(await EmployeeService(session).get(employee_id))


@router.patch("/{employee_id}")
async def update_employee(
    employee_id: uuid.UUID, body: EmployeeUpdate, session: SessionDep, _: Admin
) -> EmployeeRead:
    return EmployeeRead.model_validate(await EmployeeService(session).update(employee_id, body))


add_import_routes(router, "employees")  # GET /employees/import/template, POST /employees/import
