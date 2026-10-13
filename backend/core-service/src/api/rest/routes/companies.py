import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.rest.dependencies import Admin, CurrentPrincipal, PaginationDep, SessionDep
from src.core.services.company_service import CompanyService
from src.schemas.common import Page
from src.schemas.company import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    WhitelistCreate,
    WhitelistRead,
)

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
async def list_companies(
    session: SessionDep,
    _: CurrentPrincipal,
    paging: PaginationDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> Page[CompanyRead]:
    items, total = await CompanyService(session).list(
        q=q, is_active=is_active, page=paging.page, size=paging.size
    )
    return Page[CompanyRead](
        items=[CompanyRead.model_validate(c) for c in items],
        total=total,
        page=paging.page,
        size=paging.size,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(body: CompanyCreate, session: SessionDep, _: Admin) -> CompanyRead:
    return CompanyRead.model_validate(await CompanyService(session).create(body))


@router.get("/{company_id}")
async def get_company(
    company_id: uuid.UUID, session: SessionDep, _: CurrentPrincipal
) -> CompanyRead:
    return CompanyRead.model_validate(await CompanyService(session).get(company_id))


@router.patch("/{company_id}")
async def update_company(
    company_id: uuid.UUID, body: CompanyUpdate, session: SessionDep, _: Admin
) -> CompanyRead:
    return CompanyRead.model_validate(await CompanyService(session).update(company_id, body))


# --- whitelist (admin only: it decides whose emails get processed) ------------


@router.get("/{company_id}/whitelist")
async def list_whitelist(
    company_id: uuid.UUID, session: SessionDep, _: Admin
) -> list[WhitelistRead]:
    entries = await CompanyService(session).list_whitelist(company_id)
    return [WhitelistRead.model_validate(e) for e in entries]


@router.post("/{company_id}/whitelist", status_code=status.HTTP_201_CREATED)
async def add_whitelist(
    company_id: uuid.UUID, body: WhitelistCreate, session: SessionDep, _: Admin
) -> WhitelistRead:
    entry = await CompanyService(session).add_whitelist(company_id, body.value)
    return WhitelistRead.model_validate(entry)


@router.delete("/{company_id}/whitelist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_whitelist(
    company_id: uuid.UUID, entry_id: uuid.UUID, session: SessionDep, _: Admin
) -> None:
    await CompanyService(session).remove_whitelist(company_id, entry_id)
