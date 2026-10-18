def db_safe(text: str) -> str:
    """Remove NUL characters: PostgreSQL text and JSONB cannot store them, and one NUL in
    an email or a PDF's text would make every save of it fail."""
    return text.replace("\x00", "")
