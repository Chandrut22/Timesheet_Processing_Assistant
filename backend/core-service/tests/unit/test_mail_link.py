"""mail_url(): the "Open in Gmail" link for an email submission (pure, no database)."""

import pytest

from src.config.settings import settings
from src.schemas.submission import SubmissionRead
from src.utils.mail_link import mail_url

GMAIL = settings.mailbox_link_template
BOX = "timesheets@genworx.example"


def test_gmail_link_for_an_email() -> None:
    url = mail_url("email", "<CAB+x/y=z@mail.gmail.com>", BOX, GMAIL)
    assert url == (
        "https://mail.google.com/mail/?authuser=timesheets@genworx.example#search/rfc822msgid%3ACAB%2Bx%2Fy%3Dz%40mail.gmail.com"
    )


def test_brackets_and_spaces_are_removed() -> None:
    assert mail_url("email", "  <a@b.c>  ", BOX, GMAIL) == mail_url(
        "email", "a@b.c", BOX, GMAIL
    )


@pytest.mark.parametrize(
    ("source", "message_id", "account"),
    [
        ("upload", "<a@b.c>", BOX),  # uploads were never emails
        ("email", None, BOX),
        ("email", "", BOX),
        ("email", "<>", BOX),
        (
            "email",
            "<uid-7-42@imap.local>",
            BOX,
        ),  # made up by the listener: not in Gmail
        ("email", "<a@b.c>", None),  # MAILBOX_ACCOUNT not set: the feature is off
        ("email", "<a@b.c>", ""),
    ],
)
def test_no_link(source: str, message_id: str | None, account: str | None) -> None:
    assert mail_url(source, message_id, account, GMAIL) is None


def test_other_providers_only_need_a_template() -> None:
    template = "https://mail.example/{account}/find?id={message_id}"
    assert mail_url("email", "<a@b.c>", BOX, template) == (
        "https://mail.example/timesheets@genworx.example/find?id=a%40b.c"
    )


def test_the_api_sends_the_link_but_not_the_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mailbox_account", BOX)
    data: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "source": "email",
        "status": "processed",
        "state": "approved",
        "state_reason": None,
        "company_id": None,
        "sender_email": "payroll@lakeside.example",
        "subject": "Timesheets",
        "uploaded_by_id": None,
        "uploaded_by_name": None,
        "received_at": "2026-10-20T09:00:00Z",
        "processed_at": None,
        "error": None,
        "attempts": 1,
        "retry_at": None,
        "created_at": "2026-10-20T09:00:00Z",
        "updated_at": "2026-10-20T09:00:00Z",
        "created_by": None,
        "updated_by": None,
        "documents": [],
        "message_id": "<a@b.c>",
    }
    body = SubmissionRead.model_validate(data).model_dump(mode="json")
    assert body["mail_url"].endswith("rfc822msgid%3Aa%40b.c")
    assert "message_id" not in body

    monkeypatch.setattr(settings, "mailbox_account", None)
    assert SubmissionRead.model_validate(data).model_dump()["mail_url"] is None
