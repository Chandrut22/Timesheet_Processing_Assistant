"""Spot files that can't be read before any reader gets them: damaged files and
password-protected ones. The answer is a message a reviewer can act on (it is shown on
the document and logged against the Read step), or None when the file opens.

Checked by opening the file, never by trusting its name: a password-protected Word or
Excel file is an encrypted container (not a zip), a damaged PDF does not open in
PDFium, and a damaged image does not open in Pillow."""

import io
import zipfile

from src.constants.file_types import IMAGE_EXTENSIONS

# Office files saved with a password are an encrypted OLE container, not a zip.
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PDFIUM_PASSWORD_ERROR = 4  # FPDF_ERR_PASSWORD


def password_message(filename: str) -> str:
    return f"'{filename}' is password-protected. Ask the sender for a copy without a password."


def damaged_message(filename: str) -> str:
    return f"'{filename}' is damaged or not a valid file. Ask the sender to resend it."


def _pdf_problem(filename: str, data: bytes) -> str | None:
    import pypdfium2

    try:
        document = pypdfium2.PdfDocument(data)
    except pypdfium2.PdfiumError as exc:
        if getattr(exc, "err_code", None) == PDFIUM_PASSWORD_ERROR:
            return password_message(filename)
        return damaged_message(filename)
    except Exception:
        return damaged_message(filename)
    try:
        if len(document) == 0:
            return damaged_message(filename)
    finally:
        document.close()
    return None


def _office_problem(filename: str, data: bytes) -> str | None:
    if data.startswith(OLE_MAGIC):
        return password_message(filename)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if "[Content_Types].xml" not in archive.namelist():
                return damaged_message(filename)
    except zipfile.BadZipFile:
        return damaged_message(filename)
    return None


def _image_problem(filename: str, data: bytes) -> str | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()  # reads the whole file: a cut-off or garbled image fails here
    except Exception:
        return damaged_message(filename)
    return None


def file_problem(filename: str, extension: str, data: bytes) -> str | None:
    """Why this file can't be read (damaged / password-protected), or None."""
    if extension == ".pdf":
        return _pdf_problem(filename, data)
    if extension in (".docx", ".xlsx"):
        return _office_problem(filename, data)
    if extension in IMAGE_EXTENSIONS:
        return _image_problem(filename, data)
    return None  # CSV / TXT: any bytes can be decoded
