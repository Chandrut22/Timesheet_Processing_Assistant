# Clears test data from the core database. Asks what to delete:
#   1. Timesheet data: emails / uploads, documents and their text, timesheets and their
#      versions, the step log and state history, reprocess runs, payroll exports, their
#      audit events, and the uploaded files still waiting on the uploads volume.
#   2. Company data: companies (rates and rules), employees, allowed senders, holidays
#      and all audit events. Timesheets point to companies and employees, so deleting
#      company data always deletes the timesheet data too.
#
# Always kept: users and logins (auth schema), the database version (alembic), and the
# mailbox position in Redis (old emails are not read again).
#
# Usage (from backend\, stack running):
#   .\reset-test-data.ps1                        # asks both questions, then asks you to type RESET
#   .\reset-test-data.ps1 -Timesheets -Yes       # timesheet data only, no questions (for scripts)
#   .\reset-test-data.ps1 -Companies -Yes        # company AND timesheet data, no questions
#
# This cannot be undone. For a copy first:
#   docker compose exec -T postgres sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -n core' > core-backup.sql

param(
  [switch]$Timesheets,  # delete the timesheet data without asking
  [switch]$Companies,   # delete the company data (and so the timesheet data) without asking
  [switch]$Yes          # skip the RESET confirmation
)
$ErrorActionPreference = "Stop"

function Sql([string]$sql) {
  # SQL goes in on stdin: Windows PowerShell 5.1 mangles quotes inside native arguments.
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  $out = ($sql | & docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB -At' 2>&1 | Out-String)
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  if ($code -ne 0) { throw "psql failed: $out" }
  return $out.Trim()
}

function Ask([string]$question) {
  # y / yes = true; anything else (Enter included) = false.
  $answer = Read-Host "$question [y/N]"
  return $answer.Trim() -match '^(y|yes)$'
}

# What each choice deletes. Audit events are split: timesheet data takes only its own
# events (timesheet / submission / export); company data takes the rest.
$timesheetTables = @("submissions", "documents", "timesheets", "timesheet_versions",
                     "processing_steps", "submission_state_changes", "reprocess_runs",
                     "export_batches")
$companyTables = @("companies", "employees", "whitelist_senders", "holidays")
$timesheetAudit = "entity_type IN ('timesheet', 'submission', 'export')"

# Every row count shown, as "label|SQL".
$checks = [ordered]@{}
foreach ($t in $timesheetTables + $companyTables) { $checks[$t] = "select count(*) from core.$t" }
$checks["audit_events (timesheet data)"] = "select count(*) from core.audit_events where $timesheetAudit"
$checks["audit_events (company data)"] = "select count(*) from core.audit_events where not ($timesheetAudit)"

function Counts {
  $parts = foreach ($label in $checks.Keys) { "select '$label' || '|' || ($($checks[$label]))" }
  $rows = (Sql (($parts -join " union all ") + ";")) -split "`n" | Where-Object { $_ -match '\S' }
  $map = [ordered]@{}
  foreach ($r in $rows) { $label, $n = $r.Trim() -split "\|"; $map[$label] = [int]$n }
  return $map
}

function Show([string]$title, [string]$color, [string[]]$labels, $counts) {
  Write-Host "`n$title" -ForegroundColor $color
  foreach ($l in $labels) { "  {0,-32} {1,7}" -f $l, $counts[$l] }
}

$before = Counts
Show "Timesheet data" Yellow ($timesheetTables + "audit_events (timesheet data)") $before
Show "Company data" Yellow ($companyTables + "audit_events (company data)") $before

# --- the questions -----------------------------------------------------------------
$doCompanies = [bool]$Companies
$doTimesheets = [bool]$Timesheets -or $doCompanies
if (-not $doTimesheets) {
  Write-Host ""
  $doTimesheets = Ask "Delete the timesheet data?"
  $doCompanies = Ask "Delete the company data too (companies, employees, allowed senders, holidays)?"
  if ($doCompanies -and -not $doTimesheets) {
    Write-Host "Timesheets belong to companies and employees: the timesheet data will be deleted too." -ForegroundColor Yellow
    $doTimesheets = $true
  }
}
if (-not $doTimesheets) { Write-Host "`nNothing selected. Nothing was changed." -ForegroundColor Cyan; exit 0 }

$deleted = $timesheetTables + "audit_events (timesheet data)"
$kept = $companyTables + "audit_events (company data)"
if ($doCompanies) { $deleted += $kept; $kept = @() }

Show "Will be deleted" Red $deleted $before
if ($kept.Count) { Show "Kept" Green $kept $before }
Write-Host "  (users, logins and the mailbox position are always kept)" -ForegroundColor DarkGray

if (-not $Yes) {
  $answer = Read-Host "`nType RESET to delete the rows above (anything else cancels)"
  # Spaces and invisible characters around the word (some terminals add them) are ignored,
  # and so is the case: "RESET", "reset " and "Reset" all go ahead.
  $typed = ($answer -replace '[^A-Za-z]', '')
  if ($typed -ne "RESET") {
    Write-Host ("Cancelled: you typed '{0}' ({1} characters), not RESET. Nothing was changed." -f $answer, $answer.Length) -ForegroundColor Cyan
    exit 0
  }
}

# --- delete ------------------------------------------------------------------------
# One transaction: all or nothing. No CASCADE: if a table outside these lists ever pointed
# at these rows, PostgreSQL refuses instead of deleting more than intended.
$tables = $timesheetTables
if ($doCompanies) { $tables += $companyTables }
$list = ($tables | ForEach-Object { "core.$_" }) -join ", "
if ($doCompanies) { $audit = "TRUNCATE core.audit_events;" }
else { $audit = "DELETE FROM core.audit_events WHERE $timesheetAudit;" }
Sql "BEGIN; TRUNCATE $list; $audit COMMIT;" | Out-Null

# Uploaded files that were still waiting for the worker (the rows pointing to them are gone).
$old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
& docker compose exec -T core-service sh -c 'rm -f /data/uploads/*.bin' 2>&1 | Out-Null
$ErrorActionPreference = $old

# --- check -------------------------------------------------------------------------
$after = Counts
Show "After" Cyan ($deleted + $kept) $after
$ok = ($deleted | Where-Object { $after[$_] -ne 0 }).Count -eq 0 -and
      ($kept | Where-Object { $after[$_] -ne $before[$_] }).Count -eq 0
if (-not $ok) { Write-Host "`nSomething is off: check the counts above." -ForegroundColor Red; exit 1 }
if ($doCompanies) { Write-Host "`nDone: company and timesheet data deleted." -ForegroundColor Green }
else { Write-Host "`nDone: timesheet data deleted, company data kept." -ForegroundColor Green }