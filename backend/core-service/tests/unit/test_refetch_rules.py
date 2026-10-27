"""When Reprocess may fetch an email again, how a made-up Message-ID is read, and that
the mailbox search is read-only (folders opened read-only, nothing marked as read)."""

from email.message import EmailMessage
from typing import Any

import pytest

from src.config.settings import settings
from src.core.services.failures import MailboxRefusedError, MailboxUnavailableError, explain
from src.handlers.email.imap_source import ImapSource, placeholder_uid
from src.utils.refetch import refetch_blocker


def test_who_can_be_fetched_again() -> None:
    ok = {"enabled": True, "imap_ready": True}
    assert refetch_blocker("email", "<a@b>", **ok) is None
    assert "upload the file again" in (refetch_blocker("upload", None, **ok) or "")
    assert "EMAIL_REFETCH_ENABLED" in (
        refetch_blocker("email", "<a@b>", enabled=False, imap_ready=True) or ""
    )
    assert "IMAP_HOST" in (refetch_blocker("email", "<a@b>", enabled=True, imap_ready=False) or "")
    assert "no Message-ID" in (refetch_blocker("email", " ", **ok) or "")


def test_made_up_message_ids() -> None:
    assert placeholder_uid("<uid-1700000000-42@imap.local>") == (1700000000, 42)
    assert placeholder_uid("<CAF=abc@mail.gmail.com>") is None
    assert placeholder_uid("<uid-x-42@imap.local>") is None


def test_mailbox_errors_are_explained() -> None:
    down = explain(MailboxUnavailableError("timed out"))
    assert down.temporary and "mail server could not be reached" in down.message
    refused = explain(MailboxRefusedError("the login was refused"))
    assert not refused.temporary and "IMAP_PASSWORD" in refused.advice


class FakeFolder:
    def __init__(self, existing: set[str], validity: int = 7) -> None:
        self.existing = existing
        self.selected: list[tuple[str, bool]] = []
        self.validity = validity

    def set(self, folder: str, readonly: bool = False) -> None:
        from imap_tools.errors import MailboxFolderSelectError

        if folder not in self.existing:
            raise MailboxFolderSelectError(("NO", [b"no such folder"]), "OK")
        self.selected.append((folder, readonly))

    def status(self, folder: str, items: Any) -> dict[str, int]:
        return {"UIDVALIDITY": self.validity, "UIDNEXT": 100}


class FakeMsg:
    def __init__(self, obj: EmailMessage) -> None:
        self.obj = obj


class FakeMailbox:
    def __init__(self, folder: FakeFolder, found_in: str | None) -> None:
        self.folder = folder
        self.found_in = found_in
        self.fetches: list[tuple[str, bool]] = []

    def fetch(self, criteria: Any, mark_seen: bool = True, **_: Any) -> list[FakeMsg]:
        self.fetches.append((str(criteria), mark_seen))
        current = self.folder.selected[-1][0]
        if current == self.found_in:
            m = EmailMessage()
            m["Message-ID"] = "<a@b>"
            return [FakeMsg(m)]
        return []


def source_with(mailbox: FakeMailbox) -> ImapSource:
    source = ImapSource()
    source._mailbox = mailbox  # type: ignore[assignment]
    return source


def test_searches_the_inbox_then_the_other_folders_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "imap_folder", "INBOX")
    folder = FakeFolder({"INBOX", "[Gmail]/All Mail"})
    mailbox = FakeMailbox(folder, found_in="[Gmail]/All Mail")
    found = source_with(mailbox).find_message("<a@b>", ["Archive", "[Gmail]/All Mail"])

    assert found is not None
    assert folder.selected == [("INBOX", True), ("[Gmail]/All Mail", True)]  # Archive skipped
    assert all(mark_seen is False for _, mark_seen in mailbox.fetches)
    assert all('HEADER "Message-ID" "<a@b>"' in c for c, _ in mailbox.fetches)


def test_not_found_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "imap_folder", "INBOX")
    mailbox = FakeMailbox(FakeFolder({"INBOX"}), found_in=None)
    assert source_with(mailbox).find_message("<a@b>", ["[Gmail]/All Mail"]) is None


def test_a_made_up_id_is_found_by_uid_only_in_the_same_folder_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "imap_folder", "INBOX")
    mailbox = FakeMailbox(FakeFolder({"INBOX"}, validity=7), found_in="INBOX")
    assert source_with(mailbox).find_message("<uid-7-42@imap.local>") is not None
    assert mailbox.fetches[-1][0] == "(UID 42)"

    reset = FakeMailbox(FakeFolder({"INBOX"}, validity=8), found_in="INBOX")
    assert source_with(reset).find_message("<uid-7-42@imap.local>") is None
    assert reset.fetches == []  # the UID may belong to another email now
