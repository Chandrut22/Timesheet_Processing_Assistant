# Batch test set: 24 timesheet files (BT-01 .. BT-24)

For the Step 9 batch run: 24 uploads, one file each (like 24 emails with one
attachment), checked against the expected result and timed. Target: all done in
under 5 minutes.

Uses the seeded test data (`seed-test-data.ps1`): ABC Staffing Solutions Pvt Ltd,
Northwind Workforce Partners, BrightPath Talent Services and employees SYN-EMP-001..018.
Weeks: **A** = Mon 5 to Sun 11 Oct 2026, **B** = Mon 12 to Sun 18 Oct 2026, so they don't
clash with TC-01..TC-20 (Sep 13 to Oct 4).

## Run

```powershell
cd C:\Genworx\use_case               # the folder that holds batch-attachments\
.\run-batch.ps1                      # asks for the admin email and password
.\run-batch.ps1 -Only BT-07,BT-13     # just some cases
```

Run it once per clean week: a second run finds the first run's timesheets
(`duplicate_week`). It uses your real AI model (about 25 calls).

## The 24 files and what should happen

| Case | File | Company | Expected |
|---|---|---|---|
| BT-01 | Rahul_Kumar_Timesheet_WE_2026-10-11.xlsx | ABC | approved, 40 h |
| BT-02 | Priya_Nair_Timesheet_WE_2026-10-11.pdf | ABC | approved, 40 h |
| BT-03 | Mei_Lin_Chen_Timesheet_WE_2026-10-11.docx | ABC | approved, 40 h (Word) |
| BT-04 | Hannah_Weiss_hours_2026-10-05.csv | ABC | approved, 37.5 h (CSV) |
| BT-05 | Marcus_Allen_Timesheet_WE_2026-10-11.xlsx | NW | approved, 45 h = 40 reg + 5 OT |
| BT-06 | Elena_Petrova_Timesheet_WE_2026-10-11.pdf | NW | approved, 40 h from start / end / break times |
| BT-07 | Scan_20261012_091544.png | NW | approved or review, 40 h (scanned image, OCR) |
| BT-08 | Fatima_Zahra_Timesheet_WE_2026-10-11.xlsx | NW | approved, 44 h with a Saturday = 40 reg + 4 OT |
| BT-09 | Oliver_Grant_Timesheet_WE_2026-10-11.docx | NW | approved, 40 h |
| BT-10 | Kwame_Mensah_hours_2026-10-05.csv | NW | approved, 44 h (two 10 h days = 4 OT) |
| BT-11 | Ravi_Kumar_Timesheet_WE_2026-10-11.pdf | BP | approved, 40 h |
| BT-12 | Aisha_Rahman_Timesheet_WE_2026-10-11.xlsx | BP | approved, 32 h (Friday on leave) |
| BT-13 | IMG_20261012_1802.png | BP | approved or review, 40 h (phone photo, OCR) |
| BT-14 | Samuel_Reyes_Timesheet_WE_2026-10-11.docx | BP | approved, 40 h |
| BT-15 | Grace_Okoye_hours_2026-10-05.csv | BP | approved, 40 h |
| BT-16 | BrightPath_crew_week_2026-10-12.xlsx | BP | **5 timesheets** (crew sheet, week B), approved |
| BT-17 | Timesheet_R_Kumar_WE_2026-10-18.pdf | ABC | approved: "R. Kumar" matched by code SYN-EMP-001 |
| BT-18 | Priya_Nair_Timesheet_WE_2026-10-18.xlsx | ABC | review: **total_mismatch** (days 38, sheet says 40) |
| BT-19 | Marcus_Allen_Timesheet_WE_2026-10-18.pdf | NW | review: **long_day** (17 h on Tuesday) |
| BT-20 | John_Mathew_Timesheet_WE_2026-10-18.xlsx | NW | review: **employee_unmatched** (not on the list) |
| BT-21 | PO-88213_safety_equipment.pdf | ABC | no timesheet (a purchase order) |
| BT-22 | Oliver_Grant_Timesheet_WE_2026-10-18.docx | NW | approved, 40 h (week B) |
| BT-23 | Grace_Okoye_Timesheet_WE_2026-10-18.xlsx | BP | review: **duplicate_week** (Grace is already in BT-16; uploaded after BT-16 finishes) |
| BT-24 | Hannah_Weiss_Timesheet_WE_2026-10-18.xlsx | *none* | approved: company read from the sheet (exact name), flag company_from_sheet |

Formats: 9 Excel (one is the crew sheet), 6 PDF (one is the purchase order), 4 Word, 3 CSV, 2 images.

## Files

- `batch-attachments\BT-xx\` : one file per case
- `run-batch.ps1` : uploads, waits, checks each case, prints the timing summary
- `make_batch.py` : how the files were made (to change weeks or add cases)
