# Large documents

## What changed

| # | Before | Now |
|---|---|---|
| 1. Size check before reading | Every page and sheet was converted (slow; OCR on scans), then the text was cut at 30,000 characters | **Pages and sheets are counted first** (cheap). PDF: only pages 1–`MAX_PAGES` (50) are read. Excel: **hidden and empty sheets are never read**, and only the first `MAX_SHEETS` (30) sheets with data are read. What was left out is stored on the document (`read_limit`), and every timesheet from it gets a **`document_too_large`** flag (high): *"only pages 1-50 of 100 were read … Split the file and send it again."* With `LARGE_DOCUMENT_MODE=refuse`, the file is not read at all: *"'big.pdf' has 100 pages; the limit is 50. Split it into smaller files and send them again."* |
| 2. "Too long for the model" | The provider's "bad request" read as *"the API key or model name is not accepted"* | *"The document is too long for the AI model."* Permanent, with advice to split the file or lower `LLM_MAX_INPUT_CHARS` |
| 3. Cut-off AI answers | An answer cut at the output limit was retried 4 times, then 3 worker runs, then a generic failure | `LLM_MAX_OUTPUT_TOKENS` (16,000) is set explicitly. A cut-off answer is retried **once** asking for a shorter one. If it's cut again, the job stops with *"The AI's answer was too long … too many people or days for one answer"* (permanent, no further retries) |

The read step in the timeline says *"Read big.pdf (too large: not every page / sheet was read)"* and shows `pages_total`, `pages_read` and the skipped sheets. The documents API returns `read_limit` for each file.

## Settings (core-service, all optional)

```
MAX_PAGES=50                  # PDF pages read
MAX_SHEETS=30                 # Excel sheets with data read
LARGE_DOCUMENT_MODE=partial   # or: refuse
LLM_MAX_OUTPUT_TOKENS=16000   # empty = provider default
```

`pypdfium2` and `openpyxl` (used for counting) already come with Docling, so there are no new dependencies.

## Apply (PowerShell, from `backend/`)

```powershell
git add -A; git commit -m "Before large-document limits"
Expand-Archive -Force ..\large-documents.zip -DestinationPath .
docker compose build core-service
docker compose up -d                         # runs migration d2f6a4b8c3e5
cd core-service; uv run pytest -q; cd ..     # 207 passed
.\test-large-docs.ps1                        # 6 passed
```

`pyproject.toml` only gains a mypy setting (`openpyxl` and `pypdfium2` have no type information), so no `uv lock` is needed.

## Not included (optional, tracker item)

**Chunked extraction**: reading a long document in pieces and merging the results, so nothing is left out. Build it only if very long multi-employee sheets are normal for the clients.
