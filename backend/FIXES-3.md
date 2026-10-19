# Review fixes 3: #18 and #20

## #18 Reprocess no longer clears approvals silently

Reprocessing replaces the email's timesheets with new versions. If some of them were
already **approved** (not yet exported), the request is now refused with:

```
409  {"code": "confirmation_required",
      "detail": "1 approved timesheet(s) would be replaced and go back to review (Grace Okoye);
                 their approvals are cleared. Reprocess again with confirm_approved=true to continue."}
```

Send `"confirm_approved": true` in `POST /submissions/{id}/reprocess` to go ahead. The
audit log records which approvals were cleared (`approvals_cleared`). Exported timesheets
still can't be replaced at all.

Frontend: when the reprocess call returns 409 with `code = confirmation_required`, show
the message with a **"Replace anyway"** button that resends with `confirm_approved: true`.

## #20 No automatic approval on a guessed company

When an upload has no company, and the company is taken from the name on the sheet:

| Name on the sheet | Flag | Automatic approval |
|---|---|---|
| Exact name or a set alias ("ABC Staffing Solutions", "ABC Staff.") | `company_from_sheet` (low) | still allowed |
| Partial name ("Northwind Workforce") or close spelling ("ABC Stafing") | **`company_guessed`** (medium) | **no: a reviewer confirms** |

The guessed company is still used, so its employees and rates apply while it waits for
review. Matching the employee in review settles the flag. Emails are unchanged: the
sender's company (from the whitelist) is used as before.

## Apply (PowerShell, from `backend/`)

```powershell
git add -A; git commit -m "Before fixes 18 and 20"
Expand-Archive -Force ..\fixes-18-20.zip -DestinationPath .
docker compose build core-service
docker compose up -d
cd core-service; uv run pytest -q; cd ..       # 214 passed
```

No migration and no new packages.
