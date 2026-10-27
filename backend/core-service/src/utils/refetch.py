"""Can a reprocess fetch this submission's email again from the mailbox? Pure: the
caller passes the settings (used by the API's checks and by the submission schema)."""


def refetch_blocker(
    source: str, message_id: str | None, *, enabled: bool, imap_ready: bool
) -> str | None:
    """Why the email cannot be fetched again (a sentence that says what to do), or None
    when it can."""
    if source != "email":
        return "An upload has no copy in the mailbox: upload the file again."
    if not enabled:
        return (
            "Fetching emails again from the mailbox is turned off (EMAIL_REFETCH_ENABLED). "
            "Ask the sender to send it again."
        )
    if not imap_ready:
        return (
            "The mailbox is not set up (IMAP_HOST, IMAP_USER, IMAP_PASSWORD), so the email "
            "cannot be fetched again. Ask the sender to send it again."
        )
    if not (message_id or "").strip():
        return "This email has no Message-ID to find it by. Ask the sender to send it again."
    return None
