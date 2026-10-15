from email.message import EmailMessage

from src.handlers.email.parser import html_to_text, parse_message, sender_auth_passed


def make_email(
    *,
    sender: str = "Payroll Team <Payroll@ABCStaffing.com>",
    subject: str = "Timesheet WE 20 Sep",
    body: str = "Please find attached.",
    html: str | None = None,
    auth: list[str] | None = None,
    message_id: str | None = "<abc123@mail.abcstaffing.com>",
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "timesheets@example.com"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 21 Sep 2026 09:15:00 +0530"
    if message_id:
        msg["Message-ID"] = message_id
    for header in auth or []:
        msg["Authentication-Results"] = header
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def test_basic_fields() -> None:
    email = parse_message(make_email(), fallback_id="<fallback>")
    assert email.message_id == "<abc123@mail.abcstaffing.com>"
    assert email.from_email == "payroll@abcstaffing.com"  # lower-cased
    assert email.from_name == "Payroll Team"
    assert email.subject == "Timesheet WE 20 Sep"
    assert email.body_text == "Please find attached."
    assert email.received_at.isoformat() == "2026-09-21T09:15:00+05:30"
    assert email.attachments == []


def test_missing_message_id_uses_fallback() -> None:
    email = parse_message(make_email(message_id=None), fallback_id="<uid-1-7@imap.local>")
    assert email.message_id == "<uid-1-7@imap.local>"


def test_attachment_bytes_and_name() -> None:
    msg = make_email()
    msg.add_attachment(
        b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="Priya_Nair_WE.pdf"
    )
    email = parse_message(msg, fallback_id="x")
    assert len(email.attachments) == 1
    att = email.attachments[0]
    assert att.filename == "Priya_Nair_WE.pdf"
    assert att.content_type == "application/pdf"
    assert att.data == b"%PDF-1.4 fake"
    assert att.is_inline is False
    assert email.body_text == "Please find attached."  # attachment text is not the body


def test_inline_logo_is_marked_inline() -> None:
    msg = make_email(html='<p>Hi</p><img src="cid:logo1">')
    html_part = msg.get_payload()[1]  # type: ignore[index]
    assert isinstance(html_part, EmailMessage)
    html_part.add_related(b"\x89PNG fake", maintype="image", subtype="png", cid="<logo1>")
    email = parse_message(msg, fallback_id="x")
    assert len(email.attachments) == 1
    assert email.attachments[0].is_inline is True


def test_html_only_body_becomes_text() -> None:
    msg = EmailMessage()
    msg["From"] = "a@b.com"
    msg.set_content(
        "<html><style>p{}</style><body><p>Mon 8</p><table><tr><td>Tue</td><td>9</td></tr>"
        "</table></body></html>",
        subtype="html",
    )
    email = parse_message(msg, fallback_id="x")
    assert "Mon 8" in email.body_text
    assert "Tue\t9" in email.body_text
    assert "p{}" not in email.body_text  # styles dropped


def test_html_to_text_skips_scripts() -> None:
    text = html_to_text("<p>a</p><script>alert(1)</script><p>b</p>")
    assert "alert" not in text
    assert text.split() == ["a", "b"]


def test_encoded_subject_and_name() -> None:
    msg = make_email(
        sender="=?utf-8?b?UmHDumwgR8OzbWV6?= <raul@abc.com>", subject="=?utf-8?q?Hoja_de_horas?="
    )
    email = parse_message(msg, fallback_id="x")
    assert email.from_name == "Raúl Gómez"
    assert email.subject == "Hoja de horas"


def test_sender_auth_uses_only_the_top_header() -> None:
    passed = make_email(auth=["mx.google.com; dkim=pass; spf=pass; dmarc=pass"])
    assert sender_auth_passed(passed) is True

    failed_top = make_email(
        auth=["mx.google.com; spf=fail; dmarc=fail", "forged.example; dmarc=pass"]
    )
    assert sender_auth_passed(failed_top) is False

    spf_and_dkim = make_email(auth=["mx.example; spf=pass; dkim=pass; dmarc=none"])
    assert sender_auth_passed(spf_and_dkim) is True

    assert sender_auth_passed(make_email()) is False  # no header at all
