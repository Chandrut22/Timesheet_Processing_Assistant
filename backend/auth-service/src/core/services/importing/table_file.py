"""(Copy of core-service/src/core/services/importing/table_file.py: change both
together.)

Read an import file (CSV or XLSX) into rows of text.

Every cell is text: numbers and dates in a spreadsheet are turned into plain strings
(dates as YYYY-MM-DD), whitespace is stripped, and nothing is ever evaluated (a cell
that looks like a formula, "=HYPERLINK(...)", stays exactly that text). Only the first
sheet of a workbook is read. The file is checked first with the same magic-byte and
zip-bomb checks as timesheet uploads."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import PurePath

from src.core.exceptions import ValidationFailedError
from src.utils.file_checks import check_file, is_text

ALLOWED = (".csv", ".xlsx")


@dataclass(frozen=True, slots=True)
class Table:
    headers: list[str]  # as written in the file (stripped)
    rows: list[tuple[int, list[str]]]  # (spreadsheet row number, cells)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return (
            value.date().isoformat() if value.time() == time(0) else value.isoformat()
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return " ".join(str(value).split())


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationFailedError("The CSV file is not readable text (use UTF-8).")


def _read_csv(data: bytes) -> list[list[str]]:
    text = _decode(data)
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
            text[:4096], delimiters=",;\t"
        )
    except csv.Error:
        dialect = csv.excel
    return [
        [_text(cell) for cell in row] for row in csv.reader(io.StringIO(text), dialect)
    ]


def _read_xlsx(data: bytes) -> list[list[str]]:
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    try:
        sheet = book.worksheets[0]
        return [
            [_text(cell) for cell in row] for row in sheet.iter_rows(values_only=True)
        ]
    finally:
        book.close()


def read_table(
    filename: str,
    data: bytes,
    *,
    max_rows: int,
    max_uncompressed_mb: int,
    max_ratio: int,
) -> Table:
    """Header row + data rows (blank rows dropped). Raises ValidationFailedError (422)
    for a wrong type, an unsafe or unreadable file, no header, or too many rows."""
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValidationFailedError("Import a .csv or .xlsx file.")
    if extension == ".csv" and not is_text(data):
        raise ValidationFailedError(f"'{filename}' is not a text CSV file.")
    reason = check_file(
        filename,
        extension,
        data,
        max_uncompressed_mb=max_uncompressed_mb,
        max_ratio=max_ratio,
    )
    if reason:
        raise ValidationFailedError(reason)
    try:
        lines = _read_csv(data) if extension == ".csv" else _read_xlsx(data)
    except ValidationFailedError:
        raise
    except Exception as exc:  # a damaged workbook
        raise ValidationFailedError(f"'{filename}' could not be read: {exc}") from exc

    numbered = [(n, cells) for n, cells in enumerate(lines, start=1) if any(cells)]
    if not numbered:
        raise ValidationFailedError("The file is empty.")
    (_, headers), rows = numbered[0], numbered[1:]
    if len(rows) > max_rows:
        raise ValidationFailedError(
            f"The file has {len(rows):,} rows; the limit is {max_rows:,}. Split it."
        )
    width = len(headers)
    return Table(headers, [(n, (cells + [""] * width)[:width]) for n, cells in rows])
