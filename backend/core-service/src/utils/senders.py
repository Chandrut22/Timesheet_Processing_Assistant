import re
from enum import StrEnum

_DOMAIN_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")


class SenderKind(StrEnum):
    EMAIL = "email"
    DOMAIN = "domain"


def normalize_sender(raw: str) -> tuple[SenderKind, str]:
    """Turn what an admin typed into a clean whitelist entry.

        "Payroll@Acme.com"       -> (EMAIL,  "payroll@acme.com")
        "@acme.com" / "acme.com" -> (DOMAIN, "acme.com")

    Raises ValueError for anything else."""

    value = raw.strip().lower()
    if value.startswith("@"):
        value = value[1:]
    if "@" in value:
        local, _, domain = value.rpartition("@")
        if local and _DOMAIN_RE.match(domain):
            return SenderKind.EMAIL, value
        raise ValueError(f"'{raw}' is not a valid email address.")
    if _DOMAIN_RE.match(value):
        return SenderKind.DOMAIN, value
    raise ValueError(f"'{raw}' is not a valid email address or domain.")
