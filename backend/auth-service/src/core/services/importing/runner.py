"""(Copy of core-service/src/core/services/importing/runner.py: change both together.)

Run one import file through a resource's rules, row by row.

Each row runs inside a SAVEPOINT, so a row that breaks a rule (or a database
constraint) is undone on its own and reported, and the rows around it are not affected.
At the end:

  - dry_run=true (the default)       -> everything is rolled back: nothing is written,
                                        the report shows exactly what WOULD happen
  - on_error=abort and any row failed -> everything is rolled back (all or nothing)
  - otherwise                         -> the valid rows are committed in one transaction

Duplicates are found inside the file (the same natural key twice: the later row fails)
and against the database (on_duplicate: error / skip / update).

A resource (resources.py) only says how to read a row, what its natural key is, how to
find an existing record, and which service methods create and update one: the business
rules stay in the services (add_new / apply_changes), never copied here."""

from collections.abc import Awaitable, Callable, Hashable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, ValidationFailedError
from src.core.services.importing.table_file import Table
from src.schemas.importing import (
    CellError,
    ImportReport,
    OnDuplicate,
    OnError,
    RowResult,
)


class RowError(Exception):
    """A row that cannot be read (bad value, unknown company, ...)."""

    def __init__(self, errors: list[CellError]) -> None:
        super().__init__("; ".join(e.message for e in errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    required: bool = False
    example: str = ""
    help: str = ""


@dataclass(slots=True)
class Resource:
    """How one kind of record is imported. `parse` turns a row (column -> text) into the
    service's input and the natural key; `find` looks the key up in the database."""

    name: str
    columns: tuple[Column, ...]
    natural_key: str  # in words, for the docs and messages ("employee code + company")
    parse: Callable[[dict[str, str]], Awaitable[tuple[Any, Hashable]]]
    find: Callable[[Hashable], Awaitable[Any]]
    create: Callable[[Any], Awaitable[Any]]
    update: Callable[[Any, Any, dict[str, str]], Awaitable[Any]] | None = None
    column_alias: dict[str, str] = field(default_factory=dict)  # schema field -> column


def validation_errors(exc: ValidationError, resource: Resource) -> list[CellError]:
    """Pydantic errors, each pinned to the spreadsheet column it came from."""
    out: list[CellError] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if not isinstance(p, int)]
        column = resource.column_alias.get(loc[0], loc[0]) if loc else None
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        out.append(CellError(column=column, message=message))
    return out


def match_headers(table: Table, resource: Resource) -> tuple[dict[str, int], list[str]]:
    """Column name -> index, matched case-insensitively. Missing required columns refuse
    the whole file; unknown columns are only a warning."""
    wanted = {c.name: c for c in resource.columns}
    index: dict[str, int] = {}
    warnings: list[str] = []
    for i, header in enumerate(table.headers):
        key = header.strip().lower().replace(" ", "_")
        if key in wanted and key not in index:
            index[key] = i
        elif header.strip():
            warnings.append(
                f"Column '{header}' is not used by the {resource.name} import."
            )
    missing = [c.name for c in resource.columns if c.required and c.name not in index]
    if missing:
        raise ValidationFailedError(
            f"Missing required column(s): {', '.join(missing)}. "
            "Download the template for the exact headers."
        )
    return index, warnings


async def run_import(
    session: AsyncSession,
    resource: Resource,
    table: Table,
    *,
    file_name: str,
    dry_run: bool,
    on_error: OnError,
    on_duplicate: OnDuplicate,
    report_rows: int,
    on_commit: Callable[[ImportReport], None] | None = None,
) -> ImportReport:
    if on_duplicate == "update" and resource.update is None:
        raise ValidationFailedError(
            f"on_duplicate=update is not allowed for {resource.name}: use error or skip."
        )
    index, warnings = match_headers(table, resource)
    report = ImportReport(
        resource=resource.name,
        file_name=file_name,
        dry_run=dry_run,
        committed=False,
        on_error=on_error,
        on_duplicate=on_duplicate,
        total_rows=len(table.rows),
        warnings=warnings,
    )
    results: list[RowResult] = []
    seen: dict[Hashable, int] = {}

    for number, cells in table.rows:
        row = {name: cells[i] for name, i in index.items()}
        result = RowResult(row=number, status="failed")
        try:
            data, key = await resource.parse(row)
            if key in seen:
                message = f"Same {resource.natural_key} as row {seen[key]}."
                raise RowError([CellError(column=None, message=message)])
            seen[key] = number
            async with session.begin_nested():  # this row alone is undone on an error
                existing = await resource.find(key)
                if existing is None:
                    await resource.create(data)
                    result.status = "created"
                elif on_duplicate == "skip":
                    result.status = "skipped"
                    result.warnings.append(
                        f"Already exists ({resource.natural_key}); skipped."
                    )
                elif on_duplicate == "update" and resource.update is not None:
                    await resource.update(existing, data, row)
                    result.status = "updated"
                else:
                    message = f"Already exists ({resource.natural_key})."
                    raise RowError([CellError(column=None, message=message)])
                await session.flush()
        except RowError as exc:
            result.errors = exc.errors
        except ValidationError as exc:
            result.errors = validation_errors(exc, resource)
        except (
            AppError
        ) as exc:  # a service rule said no (conflict, inactive company, ...)
            result.errors = [CellError(column=None, message=exc.message)]
        except IntegrityError:
            result.errors = [
                CellError(column=None, message="The database refused this row.")
            ]
        results.append(result)

    for result in results:
        setattr(report, result.status, getattr(report, result.status) + 1)
    ordered: Sequence[RowResult] = sorted(
        results, key=lambda r: (r.status != "failed", r.row)
    )
    report.rows = list(ordered[:report_rows])
    report.rows_omitted = max(0, len(ordered) - report_rows)

    if dry_run or (on_error == "abort" and report.failed):
        await session.rollback()
        return report
    report.committed = True
    if on_commit is not None:
        on_commit(report)  # e.g. the audit event, saved in the same commit
    await session.commit()
    return report
