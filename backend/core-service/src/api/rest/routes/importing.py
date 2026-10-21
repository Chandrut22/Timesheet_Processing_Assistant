"""The two bulk-import endpoints, added to the employees, companies and holidays routers:

    GET  /{resource}/import/template   the CSV template (exact headers + an example row)
    POST /{resource}/import            one CSV / XLSX file; dry_run=true by default

Admins only. Counted in the "upload" rate-limit class (rate_limit.ROUTE_CLASSES)."""

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile

from src.api.rest.dependencies import Admin, SessionDep
from src.core.services.importing.service import ResourceName, import_upload, template_csv
from src.schemas.importing import ImportReport, OnDuplicate, OnError


def add_import_routes(router: APIRouter, resource: ResourceName) -> None:
    @router.get(
        "/import/template",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}, "description": "Import template (CSV)"}},
        summary=f"CSV template for importing {resource}",
    )
    async def import_template(_: Admin) -> Response:
        return Response(
            content=template_csv(resource),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{resource}-import-template.csv"'
            },
        )

    @router.post("/import", summary=f"Import {resource} from a CSV or XLSX file")
    async def import_file(
        session: SessionDep,
        actor: Admin,
        file: Annotated[UploadFile, File(description="A .csv or .xlsx file (first sheet)")],
        dry_run: Annotated[bool, Query(description="true: check only, write nothing")] = True,
        on_error: Annotated[
            OnError, Query(description="abort: nothing is written if any row fails")
        ] = "abort",
        on_duplicate: Annotated[
            OnDuplicate, Query(description="What to do with a record that already exists")
        ] = "error",
    ) -> ImportReport:
        return await import_upload(
            session,
            resource,
            file,
            actor=actor,
            dry_run=dry_run,
            on_error=on_error,
            on_duplicate=on_duplicate,
        )
