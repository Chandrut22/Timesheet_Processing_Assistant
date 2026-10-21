"""Is a file really what its extension says, and is it safe to open?

A copy of core-service/src/utils/file_checks.py (the services share no package):
change both together. Here it guards the users bulk-import file.

Checked on every upload and email attachment before anything reads it (and again for
bulk-import files):

  - magic bytes: a PDF starts with "%PDF-", DOCX / XLSX are zip packages, images have
    their own signatures, CSV / TXT must be text (no NUL bytes, decodable). A renamed
    .exe or a text file called "timesheet.pdf" is refused with a clear reason.
  - zip bombs: DOCX and XLSX are zip files, and a tiny zip can unpack to gigabytes.
    The sizes in the zip's own directory are added up BEFORE any reader opens it;
    over MAX_UNCOMPRESSED_MB, or a suspicious compression ratio, is refused. (Python's
    zipfile never unpacks more than an entry's declared size, so the directory is a
    real bound, not a hint.)

Pure functions: bytes in, None (fine) or a reason out."""

import io
import zipfile

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
_IMAGE_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": (b"BM",),
}
# The part every real Office file of that kind has.
_OFFICE_PART = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml"}
_KIND = {
    ".pdf": "PDF",
    ".docx": "Word (.docx)",
    ".xlsx": "Excel (.xlsx)",
    ".csv": "CSV",
    ".txt": "text",
}
# The ratio check only applies to files that unpack to more than this: small real files
# (a 30 KB sheet of repeated values) can compress very well without being dangerous.
RATIO_CHECK_ABOVE_BYTES = 1024 * 1024


def _kind(extension: str) -> str:
    return _KIND.get(extension, f"{extension.lstrip('.').upper()} image")


def _mismatch(filename: str, extension: str) -> str:
    return (
        f"'{filename}' is not a real {_kind(extension)} file: its content does not match "
        f"the {extension} extension."
    )


def is_text(data: bytes) -> bool:
    """No NUL bytes, and readable as UTF-8 or Windows-1252 (what Excel saves on Windows)."""
    if b"\x00" in data:
        return False
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            data.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def zip_bomb_reason(
    filename: str,
    data: bytes,
    *,
    max_uncompressed_mb: int,
    max_ratio: int,
    required_part: str | None = None,
) -> str | None:
    """Why this zip package (DOCX / XLSX) must not be opened, or None."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            entries = package.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError):
        return f"'{filename}' is damaged: it is not a readable Office (zip) file."
    names = {e.filename for e in entries}
    if required_part is not None and required_part not in names:
        return f"'{filename}' is not a real Office file (it has no {required_part})."
    unpacked = sum(e.file_size for e in entries)
    packed = sum(e.compress_size for e in entries)
    limit = max_uncompressed_mb * 1024 * 1024
    if unpacked > limit:
        return (
            f"'{filename}' unpacks to {unpacked / 1024 / 1024:,.0f} MB; the limit is "
            f"{max_uncompressed_mb} MB. Save it again, or split it."
        )
    if unpacked > RATIO_CHECK_ABOVE_BYTES and unpacked > max_ratio * max(packed, 1):
        return (
            f"'{filename}' was refused: it is compressed {unpacked // max(packed, 1):,} to 1, "
            f"which is how zip bombs look (the limit is {max_ratio} to 1)."
        )
    return None


def check_file(
    filename: str,
    extension: str,
    data: bytes,
    *,
    max_uncompressed_mb: int,
    max_ratio: int = 100,
) -> str | None:
    """None when the content matches the extension and is safe to read; otherwise the
    reason, written for the person who sent the file. Unknown extensions are not judged
    here (the supported-type check does that)."""
    head = data[:1024]
    if extension == ".pdf":
        return None if PDF_MAGIC in head else _mismatch(filename, extension)
    if extension in _OFFICE_PART:
        if not data.startswith(ZIP_MAGIC):
            return _mismatch(filename, extension)
        return zip_bomb_reason(
            filename,
            data,
            max_uncompressed_mb=max_uncompressed_mb,
            max_ratio=max_ratio,
            required_part=_OFFICE_PART[extension],
        )
    if extension in _IMAGE_MAGIC:
        return (
            None
            if data.startswith(_IMAGE_MAGIC[extension])
            else _mismatch(filename, extension)
        )
    if extension == ".webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        return None if ok else _mismatch(filename, extension)
    if extension in (".csv", ".txt"):
        return None if is_text(data) else _mismatch(filename, extension)
    return None
