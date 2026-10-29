"""Entry points the routes call: the CSV template, and importing one uploaded file."""

import csv
import hashlib
import io
import uuid
from typing import Literal

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.exceptions import ValidationFailedError
from src.core.rbac.principal import Principal
from src.core.services.audit import record_event
from src.core.services.importing.resources import COLUMNS, RESOURCES
from src.core.services.importing.runner import run_import
from src.core.services.importing.table_file import read_table
from src.schemas.importing import ImportReport, OnDuplicate, OnError

ResourceName = Literal["employees", "companies", "holidays"]


def template_csv(resource: ResourceName) -> str:
    """The exact headers and one example row (UTF-8 with BOM, so Excel opens it
    right)."""
    columns = COLUMNS[resource]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([c.name for c in columns])
    writer.writerow([c.example for c in columns])
    return "﻿" + out.getvalue()


async def import_upload(
    session: AsyncSession,
    resource: ResourceName,
    upload: UploadFile,
    *,
    actor: Principal,
    dry_run: bool,
    on_error: OnError,
    on_duplicate: OnDuplicate,
) -> ImportReport:
    max_bytes = settings.max_import_mb * 1024 * 1024
    data = await upload.read(max_bytes + 1)  # never read more than the limit
    file_name = (
        (upload.filename or "import").replace("\\", "/").rsplit("/", 1)[-1][:255]
    )
    if len(data) > max_bytes:
        raise ValidationFailedError(
            f"The file is larger than {settings.max_import_mb} MB."
        )
    if not data:
        raise ValidationFailedError("The file is empty.")
    table = read_table(
        file_name,
        data,
        max_rows=settings.max_import_rows,
        max_uncompressed_mb=settings.max_uncompressed_mb,
        max_ratio=settings.max_compression_ratio,
    )
    sha256 = hashlib.sha256(data).hexdigest()

    def audit(report: ImportReport) -> None:
        record_event(
            session,
            entity_type="import",
            entity_id=uuid.uuid4(),  # one id per committed import
            action=f"{resource}_imported",
            actor=actor,
            details={
                "resource": resource,
                "file_name": file_name,
                "sha256": sha256,
                "total_rows": report.total_rows,
                "created": report.created,
                "updated": report.updated,
                "skipped": report.skipped,
                "failed": report.failed,
                "on_error": on_error,
                "on_duplicate": on_duplicate,
            },
        )

    return await run_import(
        session,
        RESOURCES[resource](session),
        table,
        file_name=file_name,
        dry_run=dry_run,
        on_error=on_error,
        on_duplicate=on_duplicate,
        report_rows=settings.import_report_rows,
        on_commit=audit,
    )
