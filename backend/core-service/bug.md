# Codebase Bug Report

This document outlines the bugs and architectural risks identified during the comprehensive audit of the `core-service` codebase.

## 🔴 Critical / High Severity

### 1. Potential Uncommitted Data in API Routes
- **File Path:** `src/api/rest/routes/` (specifically `companies.py`, `employees.py`, `holidays.py`)
- **Type:** Logic / Data Integrity
- **Explanation:** Many API routes call service methods that perform database operations (e.g., `CompanyService(session).create(body)`). While some services call `session.commit()`, many do not. If the `SessionDep` (via `get_session`) does not explicitly commit at the end of the request lifecycle, changes may be lost despite a success response.
- **Failure Scenario:** A user creates a company via `/companies` and receives a `201 Created` response, but the data is not persisted in the database because no `commit()` was executed.
- **Recommended Fix:** Implement a consistent commit strategy. Either ensure all service methods that modify state call `session.commit()` or implement a FastAPI middleware/dependency that commits the session automatically upon a successful request.

### 2. Race Condition in Email Intake
- **File Path:** `src/core/services/email_intake_service.py` (lines 160-164)
- **Type:** Logic / Race Condition
- **Explanation:** The service checks for duplicate emails via `_already_received` before calling `session.flush()`. If multiple listeners process the same email simultaneously, both may pass the initial check. Although the `IntegrityError` on `message_id` prevents duplicate database entries, it leads to wasted processing and redundant Redis buffer writes.
- **Failure Scenario:** Under high email volume, multiple listeners trigger `IntegrityError` rollbacks and duplicate `put_file` calls to Redis, degrading performance.
- **Recommended Fix:** Use a distributed lock (e.g., via Redis) based on the `message_id` before beginning the intake process to ensure only one listener handles a specific email.

---

## 🟡 Medium Severity

### 3. Inconsistent Role Guards on Audit Routes
- **File Path:** `src/api/rest/routes/audit.py`
- **Type:** Security / RBAC
- **Explanation:** The `list_audit_events` route is guarded by the `Reviewer` role. Audit logs contain sensitive operational data. Depending on security policy, global access to audit logs might be too permissive for a standard `Reviewer` and should be restricted to `Admin` or `SuperAdmin`.
- **Failure Scenario:** A user with `Reviewer` privileges could scrape the system's entire audit history, gaining insights into administrative changes or other users' activities.
- **Recommended Fix:** Review the RBAC policy and consider restricting global audit access to the `Admin` role.

### 4. AI Extraction Failure Handling
- **File Path:** `src/core/services/processing_service.py` (lines 420-436)
- **Type:** Reliability
- **Explanation:** In the `_extract` method, any exception from the LLM-based `extract_timesheets` causes the entire submission to fail and be retried. If a specific document is "poisoned" (causes the LLM to consistently fail/timeout), the system will waste resources retrying the same failure until `worker_max_attempts` is reached.
- **Failure Scenario:** A malformed PDF causes the LLM to crash every time. The worker retries the extraction 5-10 times per submission, wasting API credits and processing time before finally marking it as `FAILED`.
- **Recommended Fix:** Implement "poison pill" detection. If a document fails deterministically, mark that specific document as failed rather than retrying the entire submission.

---

## 🔵 Low Severity

### 5. Missing Deep Input Validation
- **File Path:** `src/api/rest/routes/timesheets.py` (and other schemas)
- **Type:** Security / Validation
- **Explanation:** While Pydantic schemas are used for type safety, there is a lack of range validation on critical fields. For example, `hours` could be negative, or `work_date` could be set to an impossible future date.
- **Failure Scenario:** A user submits a timesheet with `-100` hours, which could break payroll calculations or report aggregates.
- **Recommended Fix:** Add Pydantic constraints to schemas (e.g., `Field(ge=0)` for hours) and implement custom validators for date ranges.
