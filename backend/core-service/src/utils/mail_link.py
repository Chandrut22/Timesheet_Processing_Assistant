"""Links that open an email in the mailbox's web app ("Open in Gmail").

mail_url() is pure: give it the submission's source and Message-ID, the mailbox account
and the link template (MAILBOX_ACCOUNT, MAILBOX_LINK_TEMPLATE). Gmail finds any message
by its Message-ID (search "rfc822msgid:"), and ?authuser= opens the right account when
the reviewer is signed in to several. Gmail itself decides who may see the message."""

from urllib.parse import quote

# Made up by the listener when an email has no Message-ID: no mailbox can find it.
PLACEHOLDER_SUFFIX = "@imap.local>"


def mail_url(source: str, message_id: str | None, account: str | None, template: str) -> str | None:
    """The link, or None: uploads, no / placeholder Message-ID, no account set."""
    if source != "email" or not account or not message_id:
        return None
    message_id = message_id.strip()
    if message_id.endswith(PLACEHOLDER_SUFFIX):
        return None
    bare = message_id.removeprefix("<").removesuffix(">").strip()
    if not bare:
        return None
    return template.format(
        account=quote(account.strip(), safe="@"), message_id=quote(bare, safe="")
    )
