"""Role groups, so routes say WHO may call them in one word.

admin    - master data (companies, rates, employees, whitelist, holidays, and their bulk
           import) and users, plus everything a reviewer does
reviewer - upload, review (edit hours, match, recalculate, approve / reject, bulk),
           reprocess, payroll export (preview, create, download as CSV or Excel), read
           the lists and the audit log
Any signed-in user is an admin or a reviewer, so read-only routes use CurrentPrincipal."""

from src.constants.roles import RoleName

ADMINS = frozenset({RoleName.ADMIN})
REVIEWERS = frozenset({RoleName.ADMIN, RoleName.REVIEWER})
