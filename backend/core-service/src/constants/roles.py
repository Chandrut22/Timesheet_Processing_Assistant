from enum import StrEnum


class RoleName(StrEnum):
    """Same values as auth-service's roles.name; they arrive in the JWT "role" claim.
    A token with any other role (e.g. an old "super_admin" one) is rejected."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
