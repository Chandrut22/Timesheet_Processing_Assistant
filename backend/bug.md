# Full Codebase Bug Report

## High Severity
- **Empty Core Files**: Multiple critical files in `core-service` are completely empty, suggesting a partial implementation or data loss:
    - `core-service/src/api/rest/app.py`
    - `core-service/src/handlers/http_clients/auth_client.py`
    - `core-service/src/handlers/http_clients/llm_client.py`
    - `core-service/src/handlers/email/imap_client.py`
    - `core-service/src/control/agents/timesheet_agent/nodes/extract.py`
    - `core-service/src/control/agents/timesheet_agent/nodes/match.py`
    - `core-service/src/control/agents/timesheet_agent/nodes/apply_rules.py`
    - `core-service/src/control/agents/timesheet_agent/nodes/summarize.py`
- **Missing `app.py` in Auth Service**: `auth-service/src/api/rest/app.py` is also empty.

## Medium Severity
- **Refresh Token Revocation**: `auth-service` implements token rotation but lacks a mechanism to blacklist or revoke refresh tokens. If a refresh token is stolen, it remains valid until expiry regardless of other security events.

## Low Severity / Improvements
- **Inconsistent Sanitization**: `UserService.create` does not strip user names, whereas `UserService.update` does.
- **Redundant Logic**: Email `.strip().lower()` is performed both in the route and the repository in `auth-service`.
