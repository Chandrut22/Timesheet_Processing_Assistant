import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from src.api.rest.dependencies import PaginationDep, Reviewer, SessionDep
from src.core.services.export_service import ExportService
from src.core.services.payroll_xlsx import MEDIA_TYPE as XLSX_MEDIA_TYPE
from src.core.services.payroll_xlsx import build_xlsx, xlsx_filename
from src.data.repositories.export_repository import ExportRepository
from src.schemas.common import Page
from src.schemas.export import ExportBatchRead, ExportCreate, ExportPreview

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/preview")
async def preview_export(
    company_id: uuid.UUID, week_start: date, session: SessionDep, _: Reviewer
) -> ExportPreview:
    """What the payroll sheet would contain right now. Changes nothing."""
    result = await ExportService(session).preview(company_id, week_start)
    return ExportPreview.from_result(result)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_export(
    body: ExportCreate, session: SessionDep, actor: Reviewer
) -> ExportBatchRead:
    """Create the payroll sheet and mark its timesheets as exported."""
    batch = await ExportService(session).create(
        body.company_id, body.week_start, actor, allow_pending=body.allow_pending
    )
    return ExportBatchRead.model_validate(batch)


@router.get("")
async def list_exports(
    session: SessionDep,
    _: Reviewer,
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
async def get_export(
    batch_id: uuid.UUID, session: SessionDep, _: Reviewer
) -> ExportBatchRead:
    return ExportBatchRead.model_validate(await ExportService(session).get(batch_id))


@router.get(
    "/{batch_id}/download",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}, XLSX_MEDIA_TYPE: {}},
            "description": "The payroll sheet: CSV (default) or Excel (format=xlsx)",
        }
    },
)
async def download_export(
    batch_id: uuid.UUID,
    session: SessionDep,
    _: Reviewer,
    file_format: Annotated[
        Literal["csv", "xlsx"],
        Query(alias="format", description="csv (default) or xlsx (Excel workbook)"),
    ] = "csv",
) -> Response:
    """Download a payroll export. Both formats hold the same rows: the workbook is
    built from the CSV saved with the export."""
    batch = await ExportService(session).get(batch_id)
    if file_format == "xlsx":
        return Response(
            content=build_xlsx(
                batch.csv_content,
                title=f"Payroll {batch.company_name} {batch.week_start.isoformat()}",
            ),
            media_type=XLSX_MEDIA_TYPE,
            headers={
                "Content-Disposition": "attachment; "
                f'filename="{xlsx_filename(batch.filename)}"'
            },
        )
    # The BOM makes Excel open the file as UTF-8 (names with accents stay correct).
    return Response(
        content="\ufeff" + batch.csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{batch.filename}"'},
    )
