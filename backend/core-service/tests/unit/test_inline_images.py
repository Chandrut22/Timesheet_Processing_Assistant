"""A photo pasted into the email body (inline, as phones and Gmail do) is read like an
attachment. Only small inline images (logos, icons, signature banners) are skipped."""

import io
import os
from email.message import EmailMessage

from PIL import Image

from src.constants.timesheet_status import DocumentStatus
from src.core.services.email_intake_service import document_for
from src.handlers.email.parser import Attachment, parse_message
from tests.unit.test_email_parser import make_email


def picture(width: int, height: int, fmt: str = "JPEG") -> bytes:
    """Noise, so the file is well over the 20 KB small-image limit."""
    image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    out = io.BytesIO()
    image.save(out, format=fmt, quality=90)
    return out.getvalue()


def inline(data: bytes, filename: str = "1000248415.jpg", mime: str = "image/jpeg") -> Attachment:
    return Attachment(filename=filename, content_type=mime, data=data, is_inline=True)


def test_a_photo_in_the_email_body_is_read() -> None:
    document, read = document_for(inline(picture(1200, 1600)))
    assert read and document.status == DocumentStatus.PENDING and document.error is None


def test_a_photo_pasted_from_a_phone_is_found_in_the_email() -> None:
    msg = make_email(html='<p>Timesheet attached</p><img src="cid:photo1">')
    html_part = msg.get_payload()[1]  # type: ignore[index]
    assert isinstance(html_part, EmailMessage)
    html_part.add_related(  # as Gmail sends it: inline, with a name and a Content-ID
        picture(900, 1200),
        maintype="image",
        subtype="jpeg",
        cid="<photo1>",
        disposition="inline",
        filename="1000248415.jpg",
    )
    (attachment,) = parse_message(msg, fallback_id="x").attachments
    assert attachment.is_inline
    document, read = document_for(attachment)
    assert read, document.error


def test_logos_and_signature_banners_are_still_skipped() -> None:
    for width, height in ((200, 200), (900, 120)):  # logo, signature banner
        document, read = document_for(
            inline(picture(width, height, "PNG"), "logo.png", "image/png")
        )
        assert not read and document.status == DocumentStatus.UNSUPPORTED
        assert document.error is not None and "logo or email signature" in document.error


def test_an_unnamed_inline_photo_gets_its_type_from_the_mime_type() -> None:
    document, read = document_for(inline(picture(1000, 1000), filename="unnamed"))
    assert read and document.filename == "unnamed.jpg"


def test_tiny_images_are_skipped_by_size_too() -> None:
    document, read = document_for(inline(b"\xff\xd8 tiny", "icon.jpg"))
    assert not read and document.error is not None
