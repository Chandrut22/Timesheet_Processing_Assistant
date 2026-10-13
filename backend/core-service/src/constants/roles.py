from enum import StrEnum


class RoleName(StrEnum):
    """Same values as auth-service's roles.name; they arrive in the JWT "role" claim."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
