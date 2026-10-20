"""File types the pipeline can read. Anything else is recorded as 'unsupported'."""

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",  # read directly (plain_readers.py), not by Docling
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"})
MIN_TIMESHEET_IMAGE_BYTES = 20_000  # smaller images are logos / email signatures


def skip_reason(extension: str, size_bytes: int) -> str | None:
    """Why a file should not be read at all, or None to read it."""
    if extension not in SUPPORTED_EXTENSIONS:
        return f"Unsupported file type '{extension or 'none'}'."
    if extension in IMAGE_EXTENSIONS and size_bytes < MIN_TIMESHEET_IMAGE_BYTES:
        return "Small image skipped (looks like a logo or email signature)."
    return None
