"""Role groups, so routes say WHO may call them in one word."""

from src.constants.roles import RoleName

SUPER_ADMINS = frozenset({RoleName.SUPER_ADMIN})
ADMINS = SUPER_ADMINS | {RoleName.ADMIN}  # master data, reprocess, export
REVIEWERS = ADMINS | {RoleName.REVIEWER}  # upload, review, approve
EVERYONE = frozenset(RoleName)  # read-only views (viewer included)
