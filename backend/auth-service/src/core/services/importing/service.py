"""Entry points the routes call: the CSV template, and importing one uploaded file."""

import csv
import hashlib
import io
import logging

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.exceptions import ValidationFailedError
from src.core.services.importing.runner import run_import
from src.core.services.importing.table_file import read_table
from src.core.services.importing.users import USER_COLUMNS, Welcome, users
from src.data.models import User
from src.schemas.importing import ImportReport, OnDuplicate, OnError

logger = logging.getLogger(__name__)


def template_csv() -> str:
    """The exact headers and one example row (UTF-8 with BOM, so Excel opens it
    right)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([c.name for c in USER_COLUMNS])
    writer.writerow([c.example for c in USER_COLUMNS])
    return "﻿" + out.getvalue()


async def import_users(
    session: AsyncSession,
    upload: UploadFile,
    *,
    actor: User,
    dry_run: bool,
    on_error: OnError,
    on_duplicate: OnDuplicate,
) -> tuple[ImportReport, list[Welcome]]:
    """The report, and the welcome emails to send. The list is empty unless the rows
    were committed: a dry run or an aborted import never emails anyone."""
    max_bytes = settings.max_import_mb * 1024 * 1024
    data = await upload.read(max_bytes + 1)  # never read more than the limit
    name = (upload.filename or "import").replace("\\", "/").rsplit("/", 1)[-1][:255]
    if len(data) > max_bytes:
        raise ValidationFailedError(
            f"The file is larger than {settings.max_import_mb} MB."
        )
    if not data:
        raise ValidationFailedError("The file is empty.")
    table = read_table(
        name,
        data,
        max_rows=min(settings.max_import_rows, settings.max_user_import_rows),
        max_uncompressed_mb=settings.max_uncompressed_mb,
        max_ratio=settings.max_compression_ratio,
    )
    welcomes: list[Welcome] = []
    report = await run_import(
        session,
        users(session, welcomes, dry_run=dry_run),
        table,
        file_name=name,
        dry_run=dry_run,
        on_error=on_error,
        on_duplicate=on_duplicate,
        report_rows=settings.import_report_rows,
    )
    if not report.committed:
        return report, []
    # auth-service has no audit table: the record of who imported what is this line.
    logger.info(
        "Users imported by %s: file=%s sha256=%s rows=%d created=%d skipped=%d "
        "failed=%d on_error=%s on_duplicate=%s",
        actor.id,
        name,
        hashlib.sha256(data).hexdigest(),
        report.total_rows,
        report.created,
        report.skipped,
        report.failed,
        on_error,
        on_duplicate,
    )
    return report, welcomes
