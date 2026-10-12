from enum import StrEnum


class RoleName(StrEnum):
    """The four roles. The values are what is stored in roles.name."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
