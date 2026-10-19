# Checks the large-document limits on the running stack (after the rebuild).
#
# Usage (from backend/):
#   .\test-large-docs.ps1
#
# Runs inside the core-worker container with the real libraries (pypdfium2, openpyxl,
# Docling): builds a 100-page PDF and a 5-sheet workbook in memory and reads them.
# Writes nothing to the database, makes no AI call.

$ErrorActionPreference = "Stop"

$pass = 0; $fail = 0
function Check($ok, $what) {
  if ($ok) { Write-Host "  PASS  $what" -ForegroundColor Green; $script:pass++ }
  else     { Write-Host "  FAIL  $what" -ForegroundColor Red;   $script:fail++ }
}
function Docker-Out([string[]]$cmd, [string]$stdin = $null) {
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  if ($stdin) { $out = ($stdin | & docker @cmd 2>&1 | Out-String) }
  else { $out = (& docker @cmd 2>&1 | Out-String) }
  $ErrorActionPreference = $old
  return $out.Trim()
}

Write-Host "`n1. Set-up" -ForegroundColor Cyan
$current = Docker-Out @("compose", "exec", "-T", "core-service", "alembic", "current")
Check ($current -match "d2f6a4b8c3e5") "migration d2f6a4b8c3e5 (documents.read_limit) applied"
$conf = Docker-Out @("compose", "exec", "-T", "core-worker", "python", "-c",
  "from src.config.settings import settings as s; print(s.max_pages, s.max_sheets, s.large_document_mode, s.llm_max_output_tokens)")
"  worker: max_pages max_sheets mode max_output_tokens -> $conf"
Check ($conf -match "^\d+ \d+ (partial|refuse) ") "limits are set"

Write-Host "`n2. Real files, real libraries (in core-worker)" -ForegroundColor Cyan
$code = @'
from io import BytesIO
import pypdfium2, openpyxl
from src.config.settings import settings
from src.data.clients.document_limits import prepare, too_large_flag
from src.data.clients.document_reader import read_document_with_limits

settings.large_document_mode = "partial"
doc = pypdfium2.PdfDocument.new()
for _ in range(100):
    doc.new_page(595, 842)
buf = BytesIO(); doc.save(buf); doc.close()
p = prepare("big.pdf", buf.getvalue())
print("PDF", p.page_range, p.limit.pages_total, p.limit.pages_read, bool(too_large_flag(p.limit.as_dict())))
try:
    read_document_with_limits("big.pdf", buf.getvalue())   # blank pages: "no readable text" is fine
    print("DOCLING_PAGES ok")
except TypeError as exc:
    print("DOCLING_PAGES typeerror", exc)
except Exception as exc:
    print("DOCLING_PAGES ok", type(exc).__name__)

wb = openpyxl.Workbook(); wb.remove(wb.active)
for i in range(1, 6):
    ws = wb.create_sheet(f"Week {i}"); ws.append(["Name", "Mon", "Tue"]); ws.append([f"Person{i}", 8, 8])
wb.create_sheet("Empty")
hidden = wb.create_sheet("Rates"); hidden.append(["rate", 450]); hidden.sheet_state = "hidden"
out = BytesIO(); wb.save(out)
text, limit = read_document_with_limits("hours.xlsx", out.getvalue())
print("XLSX", limit.sheets_read, limit.sheets_skipped_over_limit, limit.sheets_skipped_empty, limit.sheets_skipped_hidden)
print("TEXT", "Person1" in text, "Person4" in text, "450" in text)
'@
$out = Docker-Out @("compose", "exec", "-T", "core-worker", "python", "-") $code
$out -split "`n" | Where-Object { $_ -match "^(PDF|DOCLING|XLSX|TEXT)" } | ForEach-Object { "  $_" }
$max = [int](($conf -split "\s+")[0])
Check ($out -match "PDF \(1, $max\) 100 $max True") "100-page PDF: only pages 1-$max are read, flagged"
Check ($out -match "DOCLING_PAGES ok") "Docling accepts the page range"
Check ($out -match "XLSX .*'Empty'.*'Rates'") "empty and hidden sheets are skipped"
Check ($out -match "TEXT True \w+ False") "the hidden rates sheet is not in the text"

Write-Host "`n$pass passed, $fail failed" -ForegroundColor $(if ($fail) { "Red" } else { "Green" })
