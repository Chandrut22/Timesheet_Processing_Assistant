import re


def db_safe(text: str) -> str:
    """Remove NUL characters: PostgreSQL text and JSONB cannot store them, and one NUL
    in an email or a PDF's text would make every save of it fail."""
    return text.replace("\x00", "")


# "<source", "</source", "< /SOURCE", "<email", ...: the start of one of our block tags.
_BLOCK_TAG = re.compile(r"<\s*/?\s*(?:source|email)", re.IGNORECASE)


def strip_block_tags(text: str) -> str:
    """Remove every "<source" / "</source" / "<email" ... (any case, spaces allowed),
    again and again until nothing changes, so removing one cannot form another."""
    while True:
        cleaned = _BLOCK_TAG.sub("", text)
        if cleaned == text:
            return cleaned
        text = cleaned
