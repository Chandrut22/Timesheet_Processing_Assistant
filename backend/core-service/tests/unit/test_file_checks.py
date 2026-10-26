"""Files whose content does not match their extension, and zip bombs, are refused before
anything reads them."""

import io
import zipfile
from pathlib import Path

import openpyxl
import pytest
from PIL import Image

from src.core.services.documents.document_limits import DocumentTooLargeError, prepare
from src.utils.file_checks import check_file, is_text, zip_bomb_reason

FIXTURES = Path(__file__).parent.parent / "fixtures"
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 200


def check(name: str, data: bytes, **kw: int) -> str | None:
    ext = "." + name.rsplit(".", 1)[-1].lower()
    return check_file(name, ext, data, max_uncompressed_mb=kw.get("mb", 100), max_ratio=100)


def image(fmt: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 200, 200)).save(out, format=fmt)
    return out.getvalue()


def xlsx() -> bytes:
    book = openpyxl.Workbook()
    book.active.append(["Name", "Mon"])
    book.active.append(["Grace", 8])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def docx() -> bytes:
    """The smallest package Word and Docling accept as a document."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document><w:body>Grace 8</w:body></w:document>")
    return out.getvalue()


def bomb(unpacked_mb: int) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (unpacked_mb * 1024 * 1024))
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("week.pdf", (FIXTURES / "table_as_picture.pdf").read_bytes()),
        ("week.xlsx", xlsx()),
        ("week.docx", docx()),
        ("scan.png", image("PNG")),
        ("scan.jpg", image("JPEG")),
        ("scan.jpeg", image("JPEG")),
        ("scan.tiff", image("TIFF")),
        ("scan.bmp", image("BMP")),
        ("scan.webp", image("WEBP")),
        ("hours.csv", b"Name,Mon\r\nGrace,8\r\n"),
        ("hours.csv", "Name,Mon\nJosé,8\n".encode("cp1252")),
        ("notes.txt", b"Grace worked 8 h\n"),
    ],
    # Short test ids (file name and size): pytest puts the id in PYTEST_CURRENT_TEST,
    # and Windows refuses an environment variable over 32,767 characters.
    ids=lambda value: value if isinstance(value, str) else f"{len(value)}-bytes",
)
def test_a_valid_file_of_each_type_passes(name: str, data: bytes) -> None:
    assert check(name, data) is None


@pytest.mark.parametrize(
    "name", ["timesheet.pdf", "week.xlsx", "week.docx", "scan.png", "hours.csv"]
)
def test_a_renamed_exe_is_refused(name: str) -> None:
    reason = check(name, EXE)
    assert reason is not None and "does not match" in reason


def test_a_text_file_called_pdf_is_refused() -> None:
    reason = check("timesheet.pdf", b"Grace worked 40 hours this week")
    assert reason == (
        "'timesheet.pdf' is not a real PDF file: its content does not match the .pdf extension."
    )


def test_a_pdf_with_a_short_preamble_still_passes() -> None:
    assert check("week.pdf", b"\r\n%PDF-1.7\n...") is None


def test_a_zip_without_the_office_part_is_refused() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("readme.txt", "hello")
    reason = check("week.xlsx", out.getvalue())
    assert reason is not None and "xl/workbook.xml" in reason


def test_a_damaged_zip_is_refused() -> None:
    reason = check("week.docx", b"PK\x03\x04" + b"garbage" * 20)
    assert reason is not None and "damaged" in reason


def test_zip_bomb_over_the_size_limit() -> None:
    data = bomb(5)  # ~5 KB on disk, 5 MB unpacked
    assert len(data) < 50_000
    reason = check("week.xlsx", data, mb=2)
    assert reason is not None and "unpacks to 5 MB; the limit is 2 MB" in reason


def test_zip_bomb_by_compression_ratio() -> None:
    reason = check("week.xlsx", bomb(5), mb=100)
    assert reason is not None and "zip bombs" in reason


def test_small_well_compressed_files_are_fine() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", b"0" * 500_000)  # 500 KB, ratio > 100, but small
    assert zip_bomb_reason("w.xlsx", out.getvalue(), max_uncompressed_mb=100, max_ratio=100) is None


def test_the_reader_refuses_a_zip_bomb_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.settings import settings

    monkeypatch.setattr(settings, "max_uncompressed_mb", 2)
    with pytest.raises(DocumentTooLargeError, match="unpacks to 5 MB"):
        prepare("week.xlsx", bomb(5))


def test_text_detection() -> None:
    assert is_text(b"a,b\n1,2\n")
    assert not is_text(b"a,b\x00\n")


def test_unknown_extensions_are_left_to_the_type_check() -> None:
    assert check("archive.zip", EXE) is None
