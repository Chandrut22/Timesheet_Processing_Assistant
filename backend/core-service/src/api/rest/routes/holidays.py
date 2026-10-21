import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.rest.dependencies import Admin, CurrentPrincipal, SessionDep
from src.api.rest.routes.importing import add_import_routes
from src.core.services.holiday_service import HolidayService
from src.schemas.holiday import HolidayCreate, HolidayRead

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("")
async def list_holidays(
    session: SessionDep,
    _: CurrentPrincipal,
    company_id: uuid.UUID | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[HolidayRead]:
    holidays = await HolidayService(session).list(company_id=company_id, year=year)
    return [HolidayRead.model_validate(h) for h in holidays]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_holiday(body: HolidayCreate, session: SessionDep, _: Admin) -> HolidayRead:
    return HolidayRead.model_validate(await HolidayService(session).create(body))


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(holiday_id: uuid.UUID, session: SessionDep, _: Admin) -> None:
    await HolidayService(session).delete(holiday_id)


add_import_routes(router, "holidays")  # GET /holidays/import/template, POST /holidays/import
