# core-service

The timesheet pipeline and its REST API.

Docs: [architecture](docs/architecture.md) (folders, layers, a request's path) ·
[settings](docs/settings.md) (every setting) · [runbook](docs/runbook.md) (start,
checks, migrations, common problems). Development commands: the `Makefile`
(`make check`, `make run`, `make migrate`) or the PowerShell commands in the runbook.

## Photos and scanned timesheets (vision read)

Docling + RapidOCR is built for printed text and reads handwriting badly. With
`VISION_ENABLED=true`, photos (PNG, JPG, TIFF, BMP, WebP) and PDFs **without a text
layer** are read by a vision-language model instead. Typed PDFs, DOCX, XLSX, CSV and TXT
keep the Docling / plain-reader path exactly as before. It is **off by default** and
nothing is sent anywhere until it is set up.

```
Typed PDF / DOCX / XLSX / CSV ──► Docling or plain reader ──► text ─┐
                                                                     ├─► LLM extraction ─► match ─► rules ─► decide
Photo / scanned PDF ──► vision model (1 call per page) ──► text ────┘
                         classification + transcription
```

For each page (up to `VISION_MAX_PAGES`):

1. The page is turned upright (EXIF), converted to RGB and shrunk to at most
   `VISION_IMAGE_MAX_SIDE` px and about 2.5 MP; scanned PDFs are rendered at 200 DPI.
2. One call returns JSON: `classification` (printed_only / handwritten_only / mixed /
   no_text / uncertain), `confidence`, `has_handwriting`, `has_handwritten_hours`,
   `has_printed_text`, `reason` and the `transcription` (Markdown, `[UNCLEAR]` for
   anything unreadable, never guessed). A signature or initials alone stay printed_only.
3. An answer that is not that JSON is asked again once; then the page counts as
   uncertain. Confidence below `VISION_MIN_CONFIDENCE` also counts as uncertain (decided
   in code). The `[UNCLEAR]` marks are counted in code.

The pages are joined (`--- page N ---`) into `documents.extracted_text`, the same column
Docling fills, so chunking, the prompt-injection protection and reprocessing work as
before (a reprocess reuses the text: the image is never sent again). The document also
keeps `read_method`, `writing_class` (worst page wins), `writing_confidence`,
`has_handwritten_hours`, `writing_reason` and `unclear_marks`.

What the decision does with it:

| Document | Flag | Severity | Auto-approve |
|---|---|---|---|
| printed_only (confident) | none | | normal rules |
| mixed, hours printed | `handwriting_present` | low | normal rules |
| hours written by hand (or handwritten_only) | `handwritten_hours` | high | never |
| uncertain or no_text | `writing_unclear` | high | never |
| `[UNCLEAR]` values | `unreadable_values` (with the dates) | high | never |

The extraction prompt never guesses an `[UNCLEAR]` value and never uses 0 for it: the
day is listed in `unreadable_days` and left out of the timesheet.

If the vision server is down, times out or answers 5xx, the job is retried later like
any temporary failure. It is never read with OCR instead (that would guess handwriting).
Logs, traces and the step log record the method, model, pages, class, confidence,
`[UNCLEAR]` count and timings: never the image, the reason or the transcription.

### Setting it up (core-service `.env`)

Ollama Cloud (hosted by Ollama: page images of timesheets leave your network):

    VISION_ENABLED=true
    VISION_BASE_URL=https://ollama.com/v1
    VISION_API_KEY=<your Ollama API key>
    VISION_MODEL=gemma4:31b-cloud

Self-hosted Ollama (nothing leaves your network; Gemma 4 31B needs about 20 GB of GPU
memory at 4-bit):

    ollama pull gemma4:31b
    VISION_ENABLED=true
    VISION_BASE_URL=http://gpu-host:11434/v1
    VISION_MODEL=gemma4:31b

Copy the model name exactly as the server lists it. `VISION_MAX_PAGES x VISION_TIMEOUT_S
+ 300` must fit in `WORKER_JOB_TIMEOUT_SECONDS` (the settings refuse to start otherwise).
All settings: `.env.example`.

### Checking a model on your own sheets

    uv run python -m src.tools.eval_handwriting eval_data/handwritten \
        --model gemma4:31b-cloud --base-url https://ollama.com/v1 --out eval-report.md

The folder holds the images plus an `expected.csv` (`file,employee_name,work_date,hours`,
one row per day). The Markdown report gives, per file, the class the model saw, and
overall the name character error rate, date and hours exact match, the share of days
marked `[UNCLEAR]`, seconds per page and failures. `eval_data/` and `eval-report*.md`
are in `.gitignore`: never commit real timesheets.

## Long documents (read in overlapping parts)

A document longer than `CHUNK_TARGET_CHARS` (12,000 characters), or listing more than
`CHUNK_PEOPLE` (15) people, is read in parts (`core/services/chunking.py`). This applies
to every kind of text: Docling tables, vision transcriptions, free text, email bodies.

1. **Split.** Pieces of at most 12,000 characters and 15 new people, never cut inside a
   line. Near the end of a piece the best place to cut wins: a blank line, heading or page
   break, the end of a table, the start of a person block (`Employee: ...`), a row that
   starts a new person, any row. Each piece starts about `CHUNK_OVERLAP_CHARS` (1,500, at
   most a quarter of the piece) before the previous one ended, so a person on a cut is
   seen whole in one piece. The text before the first table (client, week) and, inside a
   table, its header row are repeated on top of every piece.
2. **Extract.** One AI call per piece, `CHUNK_PARALLEL` (2) at a time; the AI is told it
   reads part *k* of *n* and that the parts overlap. A failed piece is tried again on its
   own (`CHUNK_PIECE_RETRIES`, 2); if it keeps failing the job fails as before and nothing
   is saved.
3. **Combine.** The same person (employee code, else name) and week from different parts
   become one timesheet; a day read twice in the overlap is kept once. The same day with
   different hours in two parts keeps the later part's value and gets the
   `overlap_disagreement` flag (high: never auto-approved). Two timesheets from the same
   part are never joined (the duplicate rules handle them).
4. **Match.** After employee matching, timesheets from different parts matched to the
   same employee and week ("R. Kumar" in one part, "Rahul Kumar" in the next) are joined
   too. Then the pay rules and the decision run once, as for any document.

More than `CHUNK_MAX_PARTS` (40) parts: the rest is not read, and every timesheet gets
`document_too_large` with the line where reading stopped. A single block longer than
`LLM_MAX_INPUT_CHARS` gets `document_truncated`. The extract step in the processing log
lists every part (lines, characters, overlap, people, attempts, timesheets) and how many
people were combined across parts.

## Rate limit

One limit for every endpoint of both services: at most `RATE_LIMIT` requests (default
`100/60`, 100 per 60 seconds) per client IP (`src/api/middleware/rate_limit.py`, the same
file in auth-service and core-service).

- **Shared:** both services count in the same Redis counter (`rl:ip:<ip>:<window>`), so
  calls to `/auth/...` and `/api/...` from one IP add up to the same 100. Signed in or not,
  only the IP counts.
- **Sliding window:** the limit holds in any 60 seconds, not only per calendar minute.
- **Over the limit:** `429 {"detail": "Too many requests. Try again in N seconds.", "code":
  "rate_limited"}` with `Retry-After`. Every response carries `X-RateLimit-Limit`,
  `-Remaining` and `-Reset`.
- **Not counted:** health checks (`RATE_LIMIT_EXEMPT_PATHS`) and CORS preflights.
- **Client IP:** the `X-Real-IP` header nginx sets (`$remote_addr`, overwriting anything a
  browser sent); without it, the socket address. `X-Forwarded-For` is never read. Only
  nginx is reachable from outside (`docker-compose.override.yml` publishes the APIs on
  127.0.0.1 only, for development). If a load balancer is ever put in front of nginx,
  configure nginx's real-IP module (`set_real_ip_from`, `real_ip_header`) so
  `$remote_addr` is the browser again.
- **Redis down:** `RATE_LIMIT_FAIL_OPEN=true` (default) lets requests through and logs a
  warning; `false` answers 503 `rate_limit_unavailable`.
- **Settings:** `RATE_LIMIT_ENABLED`, `RATE_LIMIT`, `RATE_LIMIT_FAIL_OPEN`,
  `RATE_LIMIT_EXEMPT_PATHS`.
