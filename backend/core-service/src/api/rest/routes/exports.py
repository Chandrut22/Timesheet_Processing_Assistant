import uuid
from datetime import date

from fastapi import APIRouter, Response, status

from src.api.rest.dependencies import Admin, PaginationDep, SessionDep
from src.core.services.export_service import ExportService
from src.data.repositories.export_repository import ExportRepository
from src.schemas.common import Page
from src.schemas.export import ExportBatchRead, ExportCreate, ExportPreview

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/preview")
async def preview_export(
    company_id: uuid.UUID, week_start: date, session: SessionDep, _: Admin
) -> ExportPreview:
    """What the payroll sheet would contain right now. Changes nothing."""
    result = await ExportService(session).preview(company_id, week_start)
    return ExportPreview.from_result(result)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_export(body: ExportCreate, session: SessionDep, actor: Admin) -> ExportBatchRead:
    """Create the payroll sheet and mark its timesheets as exported."""
    batch = await ExportService(session).create(
        body.company_id, body.week_start, actor, allow_pending=body.allow_pending
    )
    return ExportBatchRead.model_validate(batch)


@router.get("")
async def list_exports(
    session: SessionDep,
    _: Admin,
    paging: PaginationDep,
    company_id: uuid.UUID | None = None,
    week_start: date | None = None,
) -> Page[ExportBatchRead]:
    items, total = await ExportRepository(session).search(
        company_id=company_id, week_start=week_start, page=paging.page, size=paging.size
    )
    return Page[ExportBatchRead](
        items=[ExportBatchRead.model_validate(b) for b in items],
        total=total,
        page=paging.page,
        size=paging.size,
    )


@router.get("/{batch_id}")
async def get_export(batch_id: uuid.UUID, session: SessionDep, _: Admin) -> ExportBatchRead:
    return ExportBatchRead.model_validate(await ExportService(session).get(batch_id))


@router.get(
    "/{batch_id}/download",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The payroll sheet (CSV)"}},
)
async def download_export(batch_id: uuid.UUID, session: SessionDep, _: Admin) -> Response:
    batch = await ExportService(session).get(batch_id)
    # The BOM makes Excel open the file as UTF-8 (names with accents stay correct).
    return Response(
        content="\ufeff" + batch.csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{batch.filename}"'},
    )
