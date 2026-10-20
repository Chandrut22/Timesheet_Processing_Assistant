from enum import StrEnum


class RoleName(StrEnum):
    """The two roles. The values are what is stored in roles.name (a CHECK on the
    table allows only these) and what the access token carries to core-service.

    admin    - everything: users, companies, employees, whitelist, holidays,
               plus every reviewer action
    reviewer - reviews timesheets: upload, edit hours, match, approve / reject,
               reprocess, payroll export (preview, create, download CSV / Excel)
    """

    ADMIN = "admin"
    REVIEWER = "reviewer"
