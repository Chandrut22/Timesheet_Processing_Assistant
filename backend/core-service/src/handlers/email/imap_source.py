"""The real mailbox, through imap-tools (IMAP over SSL + IDLE).

imap-tools is blocking, so the listener calls these methods in a thread."""

import contextlib
import functools
import imaplib
from collections.abc import Callable
from datetime import date
from email.message import Message
from types import TracebackType

from imap_tools import AND, MailBox, U

from src.config.settings import settings

FETCH_LIMIT = 50  # at most this many emails per round; the rest come next round


class MailConnectionLost(Exception):
    """The network or the mail server closed the IMAP connection (SSLEOFError, reset,
    timeout, IMAP abort, DNS down). Expected now and then on a long-lived connection: the
    listener reconnects and catches up. Database / Redis errors are never wrapped."""


def _mail_call[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (OSError, EOFError, imaplib.IMAP4.abort) as exc:
            raise MailConnectionLost(f"{type(exc).__name__}: {exc or 'closed'}") from exc

    return call


class ImapSource:
    def __init__(self) -> None:
        self._mailbox: MailBox | None = None

    @property
    def mailbox(self) -> MailBox:
        if self._mailbox is None:
            raise RuntimeError("Not connected: use 'with ImapSource() as source:'")
        return self._mailbox

    @_mail_call
    def __enter__(self) -> "ImapSource":
        if not (settings.imap_host and settings.imap_user and settings.imap_password):
            raise RuntimeError("IMAP_HOST, IMAP_USER and IMAP_PASSWORD must be set.")
        # Gmail shows App Passwords as "abcd efgh ijkl mnop": the spaces are not part of it
        password = settings.imap_password.get_secret_value().replace(" ", "")
        # The socket timeout bounds every call on a dead connection (IDLE sets its own
        # timeout for its wait and puts this one back afterwards).
        self._mailbox = MailBox(
            settings.imap_host, settings.imap_port, timeout=settings.imap_timeout_s
        ).login(settings.imap_user, password, initial_folder=settings.imap_folder)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._mailbox is None:
            return
        with contextlib.suppress(Exception):  # the connection is often already gone
            self._mailbox.client.sock.settimeout(5)  # never hang on a dead connection
        with contextlib.suppress(Exception):
            self._mailbox.logout()
        with contextlib.suppress(Exception):
            self._mailbox.client.shutdown()
        self._mailbox = None

    @_mail_call
    def status(self) -> tuple[int, int]:
        """(UIDVALIDITY, UIDNEXT) of the folder."""
        st = self.mailbox.folder.status(settings.imap_folder, ["UIDVALIDITY", "UIDNEXT"])
        return int(st["UIDVALIDITY"]), int(st["UIDNEXT"])

    @_mail_call
    def fetch_from_uid(self, start_uid: int) -> list[tuple[int, Message]]:
        # mark_seen=False: reading here must not change what people see in the mailbox
        return [
            (int(msg.uid or 0), msg.obj)
            for msg in self.mailbox.fetch(
                AND(uid=U(str(start_uid), "*")), mark_seen=False, limit=FETCH_LIMIT, bulk=True
            )
        ]

    @_mail_call
    def fetch_since(self, day: date) -> list[tuple[int, Message]]:
        return [
            (int(msg.uid or 0), msg.obj)
            for msg in self.mailbox.fetch(
                AND(date_gte=day), mark_seen=False, limit=FETCH_LIMIT, bulk=True
            )
        ]

    @_mail_call
    def wait(self, timeout: int) -> bool:
        """IMAP IDLE until the server reports a change or the timeout passes."""
        return bool(self.mailbox.idle.wait(timeout=timeout))
