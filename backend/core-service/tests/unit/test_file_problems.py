"""Damaged and password-protected files are spotted before any reader opens them, with
a message the reviewer can act on (test case 8: a corrupted attachment)."""

import io
import zipfile

import pytest
from PIL import Image

from src.config.settings import settings
from src.core.services.documents.document_reader import (
    UnreadableFileError,
    read_document_full,
)
from src.core.services.documents.file_problems import OLE_MAGIC, file_problem
from tests.fixtures.pdfs import blank_pdf, encrypted_pdf


def pdf(password: str | None = None) -> bytes:
    if password:
        return encrypted_pdf(user=password, owner="owner-" + password)
    return blank_pdf()


def docx() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return out.getvalue()


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.effect_noise((400, 300), 50).convert("RGB").save(out, format="JPEG")
    return out.getvalue()


def test_files_that_open_have_no_problem() -> None:
    assert file_problem("a.pdf", ".pdf", pdf()) is None
    assert file_problem("a.docx", ".docx", docx()) is None
    assert file_problem("a.jpg", ".jpg", jpeg()) is None
    assert file_problem("a.csv", ".csv", b"\xff\xfe any bytes") is None


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("broken.pdf", b"%PDF-1.7 this is not a real pdf" * 100),
        ("cut.pdf", pdf()[:120]),  # cut off half way (a broken download)
        ("broken.docx", b"PK\x03\x04 not really a zip" * 100),
        ("noise.xlsx", b"\x00\x01\x02" * 1000),
        ("cut.jpg", jpeg()[:500]),
        ("fake.png", b"\x89PNG not an image" * 3000),
    ],
    # Short test ids (file name and size): pytest puts the id in PYTEST_CURRENT_TEST,
    # and Windows refuses an environment variable over 32,767 characters.
    ids=lambda value: value if isinstance(value, str) else f"{len(value)}-bytes",
)
def test_damaged_files(name: str, data: bytes) -> None:
    extension = "." + name.rsplit(".", 1)[1]
    message = file_problem(name, extension, data)
    assert (
        message
        == f"'{name}' is damaged or not a valid file. Ask the sender to resend it."
    )


def test_password_protected_files() -> None:
    expected = "is password-protected. Ask the sender for a copy without a password."
    assert (
        file_problem("locked.pdf", ".pdf", pdf("secret")) == f"'locked.pdf' {expected}"
    )
    locked_word = OLE_MAGIC + b"\x00" * 4000  # Office saves an encrypted file as OLE
    assert (
        file_problem("locked.docx", ".docx", locked_word) == f"'locked.docx' {expected}"
    )
    assert (
        file_problem("locked.xlsx", ".xlsx", locked_word) == f"'locked.xlsx' {expected}"
    )


@pytest.mark.parametrize("vision", [True, False])
def test_the_reader_refuses_them_before_docling_or_the_vision_model(
    vision: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vision_enabled", vision)
    monkeypatch.setattr(settings, "vision_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "vision_model", "m")
    with pytest.raises(UnreadableFileError, match="damaged"):
        read_document_full(
            "broken.pdf", b"%PDF-1.7 garbage" * 100
        )  # the crash in the log
    with pytest.raises(UnreadableFileError, match="password-protected"):
        read_document_full("locked.pdf", pdf("secret"))
