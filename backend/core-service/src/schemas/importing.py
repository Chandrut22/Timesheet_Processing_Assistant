"""The bulk-import report: what happened to each row of the file."""

from typing import Literal

from pydantic import BaseModel, Field

RowStatus = Literal["created", "updated", "skipped", "failed"]
OnError = Literal["abort", "skip"]
OnDuplicate = Literal["error", "skip", "update"]


class CellError(BaseModel):
    column: str | None = Field(
        description="The column the problem is in; null = the whole row"
    )
    message: str


class RowResult(BaseModel):
    row: int = Field(description="Spreadsheet row number (the header is row 1)")
    status: RowStatus
    errors: list[CellError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImportReport(BaseModel):
    resource: str
    file_name: str
    dry_run: bool
    committed: bool = Field(
        description="True when the rows were written to the database"
    )
    on_error: OnError
    on_duplicate: OnDuplicate
    total_rows: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[str] = Field(
        default_factory=list, description="About the file (columns)"
    )
    rows: list[RowResult] = Field(
        default_factory=list,
        description="Row details, failed rows first, at most IMPORT_REPORT_ROWS of "
        "them",
    )
    rows_omitted: int = Field(default=0, description="Rows not listed in `rows`")
