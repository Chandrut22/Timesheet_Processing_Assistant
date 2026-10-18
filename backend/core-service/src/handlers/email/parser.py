"""Raw email (email.message.Message) -> a clean ParsedEmail. Standard library only.

Attachment bytes are kept in memory just long enough to put them in the Redis upload
buffer; nothing is written to disk."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from src.utils.text import db_safe


@dataclass(frozen=True, slots=True)
class Attachment:
    filename: str
    content_type: str
    data: bytes
    is_inline: bool  # embedded in the HTML (logos, signature images)


@dataclass(slots=True)
class ParsedEmail:
    message_id: str
    from_name: str
    from_email: str
    subject: str
    received_at: datetime
    body_text: str
    sender_auth_passed: bool
    attachments: list[Attachment] = field(default_factory=list)


# ---------------- helpers ----------------


def decode_mime_header(value: str | None) -> str:
    """'=?utf-8?b?...?=' -> readable text."""
    if not value:
        return ""
    try:
        return db_safe(str(make_header(decode_header(value)))).strip()
    except Exception:
        return db_safe(str(value)).strip()


def _decode_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    data = payload if isinstance(payload, bytes) else b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:  # unknown charset name
        return data.decode("utf-8", errors="replace")


class _HTMLToText(HTMLParser):
    BLOCK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in ("td", "th"):
            self.parts.append("\t")  # keeps table columns apart

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    return re.sub(r"\n\s*\n+", "\n\n", "".join(parser.parts)).strip()


def received_at(msg: Message) -> datetime:
    """When our mail server got it: the newest Received header, else the Date header."""
    received = msg.get_all("Received") or []
    candidates = [str(received[0]).rsplit(";", 1)[-1]] if received else []
    candidates.append(str(msg.get("Date", "")))
    for value in candidates:
        try:
            dt = parsedate_to_datetime(value.strip())
        except (TypeError, ValueError, IndexError):
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return datetime.now(UTC)


_COMMENT = re.compile(r"\([^()]*\)")


def _domain(value: str | None) -> str:
    """'Ann <ann@Mail.Example.com>' / '@example.com' / 'example.com' -> 'mail.example.com'."""
    text = (value or "").strip().strip("<>").lower()
    if "<" in text or " " in text:
        text = parseaddr(text)[1]
    return text.rsplit("@", 1)[-1].strip().rstrip(".")


def _aligned(signed: str, from_domain: str) -> bool:
    """Relaxed alignment (as DMARC uses): the same domain, or one is a subdomain of the
    other. Both must be real domains (have a dot), so 'com' never aligns with anything."""
    if not signed or not from_domain or "." not in signed or "." not in from_domain:
        return False
    return (
        signed == from_domain
        or signed.endswith("." + from_domain)
        or from_domain.endswith("." + signed)
    )


def parse_auth_results(header: str) -> list[tuple[str, str, dict[str, str]]]:
    """'mx.google.com; dkim=pass header.d=a.com; dmarc=pass header.from=a.com'
    -> [("dkim", "pass", {"header.d": "a.com"}), ("dmarc", "pass", {"header.from": "a.com"})]

    Comments in brackets are dropped first, so text such as
    '(domain of dmarc=pass@evil.example ...)' can never count as a result. The first part
    (the server name) is skipped."""
    text = header.lower()
    while _COMMENT.search(text):
        text = _COMMENT.sub(" ", text)
    results: list[tuple[str, str, dict[str, str]]] = []
    for part in text.split(";")[1:]:
        tokens = part.split()
        if not tokens or "=" not in tokens[0]:
            continue
        method, _, result = tokens[0].partition("=")
        props: dict[str, str] = {}
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if sep:
                props[key] = value.strip('"')
        results.append((method, result, props))
    return results


def sender_auth_passed(msg: Message) -> bool:
    """Did OUR mail server verify that the email really comes from the From domain?

    Only the topmost Authentication-Results header counts: it is the one our server
    added. Lower ones travel with the message and could be written by anyone.

    A pass only counts when it is for the domain in From ("aligned"), as DMARC requires.
    Otherwise an attacker could send from their own domain (passing SPF and DKIM for
    it) with a whitelisted address in From. Accepted:
      dmarc=pass with header.from = the From domain, or
      dkim=pass  with header.d (or header.i) aligned to the From domain, or
      spf=pass   with smtp.mailfrom aligned to the From domain."""
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False
    from_domain = _domain(parseaddr(str(msg.get("From") or ""))[1])
    if not from_domain:
        return False
    for method, result, props in parse_auth_results(str(headers[0])):
        if result != "pass":
            continue
        if method == "dmarc" and _domain(props.get("header.from")) == from_domain:
            return True
        if method == "dkim" and (
            _aligned(_domain(props.get("header.d")), from_domain)
            or _aligned(_domain(props.get("header.i")), from_domain)
        ):
            return True
        if method == "spf" and _aligned(_domain(props.get("smtp.mailfrom")), from_domain):
            return True
    return False


# ---------------- main entry ----------------


def parse_message(msg: Message, *, fallback_id: str) -> ParsedEmail:
    """fallback_id is used when the email has no Message-ID header."""
    texts: list[str] = []
    htmls: list[str] = []
    attachments: list[Attachment] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        mime = part.get_content_type()
        disposition = str(part.get("Content-Disposition") or "").lower()
        filename = decode_mime_header(part.get_filename())
        inline_image = mime.startswith("image/") and part.get("Content-ID") is not None

        if filename or disposition.startswith("attachment") or inline_image:
            payload = part.get_payload(decode=True)
            attachments.append(
                Attachment(
                    filename=filename or "unnamed",
                    content_type=mime,
                    data=payload if isinstance(payload, bytes) else b"",
                    is_inline=disposition.startswith("inline")
                    or (inline_image and not disposition),
                )
            )
        elif mime == "text/plain":
            texts.append(_decode_text(part))
        elif mime == "text/html":
            htmls.append(_decode_text(part))

    body = "\n".join(texts).strip() or (html_to_text("\n".join(htmls)) if htmls else "")
    body = db_safe(body)
    from_name, from_email = parseaddr(decode_mime_header(msg.get("From")))

    return ParsedEmail(
        message_id=db_safe(str(msg.get("Message-ID") or "")).strip()[:998] or fallback_id,
        from_name=from_name,
        from_email=from_email.strip().lower(),
        subject=decode_mime_header(msg.get("Subject"))[:998],
        received_at=received_at(msg),
        body_text=body,
        sender_auth_passed=sender_auth_passed(msg),
        attachments=attachments,
    )
