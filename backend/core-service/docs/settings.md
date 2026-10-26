# core-service: settings

Every setting is read from the environment (or the service's `.env`) by
`src/config/settings.py`; names are case-insensitive. Secrets have no default here: set
them in `.env` only (never committed). Generated from settings.py.

## App

| Setting | Default | What it does |
|---|---|---|
| `APP_NAME` | `"core-service"` |  |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Browser apps allowed to call this API (the frontend). In .env as JSON, e.g. CORS_ORIGINS=["https://timesheets.example.com"]. Use the same host name the browser uses (localhost and 127.0.0.1 are different origins). |
| `ENVIRONMENT` | `"dev"` |  |
| `LOG_LEVEL` | `"INFO"` |  |
| `DOCS_ENABLED` | `False` | API docs (/docs, /openapi.json). Off by default so a deployed service does not publish its full API map; DOCS_ENABLED=true in .env for local development. |
| `AUTH_PUBLIC_PATHS` | `["/health", "/health/db", "/health/redis"]` | Paths anyone may call without a token (the auth middleware denies everything else). The API docs are added automatically when DOCS_ENABLED=true; OPTIONS always passes. |

## Rate limiting (src/api/middleware/rate_limit.py)

| Setting | Default | What it does |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `True` | One limit for every endpoint: RATE_LIMIT requests ("requests/window_seconds") per client IP, shared with auth-service (same Redis counter). The IP is the X-Real-IP header nginx sets (else the socket address). Health checks are never counted. |
| `RATE_LIMIT_FAIL_OPEN` | `True` | Redis down: let requests through (False: 503) |
| `RATE_LIMIT` | `"100/60"` |  |
| `RATE_LIMIT_EXEMPT_PATHS` | `["/health", "/health/db", "/health/redis"]` |  |

## Database: shared timesheet_db, this service owns the "core" schema

| Setting | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `"postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/timesheet_db"` |  |
| `DB_POOL_SIZE` | `5` |  |
| `DB_MAX_OVERFLOW` | `10` |  |
| `DB_ECHO` | `False` |  |

## Redis: shared db 0, every key starts with "core:"

| Setting | Default | What it does |
|---|---|---|
| `REDIS_URL` | `"redis://127.0.0.1:6380/0"` |  |
| `REDIS_PREFIX` | `"core"` |  |

## JWT: core only VERIFIES tokens, so it needs only the PUBLIC key

| Setting | Default | What it does |
|---|---|---|
| `JWT_PUBLIC_KEY_PATH` | `Path("keys/jwt_public.pem")` |  |
| `JWT_ALGORITHM` | `"RS256"` |  |
| `JWT_ISSUER` | `"auth-service"` |  |
| `JWT_AUDIENCE` | `"timesheet-api"` |  |

## Uploads

| Setting | Default | What it does |
|---|---|---|
| `MAX_UPLOAD_MB` | `15` |  |
| `MAX_FILES_PER_UPLOAD` | `10` |  |
| `UPLOAD_DIR` | `Path("data/uploads")` | Uploaded / emailed files wait here (one file per document) until the worker has read them; then they are deleted. A shared Docker volume in compose. Never in Redis. |
| `UPLOAD_BUFFER_TTL_HOURS` | `72` | a file not read by then is deleted (sweeper) |
| `MAX_UNCOMPRESSED_MB` | `100` | DOCX / XLSX are zip packages: refuse one that unpacks to more than this, or that is compressed more than MAX_COMPRESSION_RATIO to 1 (how zip bombs look). Checked from the zip's directory before any reader opens the file (src/utils/file_checks.py). |
| `MAX_COMPRESSION_RATIO` | `100` |  |
| `MAX_IMPORT_MB` | `5` | Bulk import of employees / companies / holidays (CSV or XLSX, admins only). |
| `MAX_IMPORT_ROWS` | `5000` |  |
| `IMPORT_REPORT_ROWS` | `200` | row details in the response |
| `MAX_PAGES` | `50` | Big files: counted BEFORE reading (reading is the slow part, and the AI only sees the first LLM_MAX_INPUT_CHARS anyway). Hidden and empty Excel sheets are never read. PDF pages read |
| `MAX_SHEETS` | `30` | Excel sheets (with data) read |
| `LARGE_DOCUMENT_MODE` | `"partial"` | partial: read the first MAX_PAGES / MAX_SHEETS and flag document_too_large refuse:  do not read the file; "split it and send it again" |

## LLM: any OpenAI-compatible API (Groq, OpenRouter, OpenAI, Ollama, vLLM)

| Setting | Default | What it does |
|---|---|---|
| `LLM_BASE_URL` | `None` |  |
| `LLM_API_KEY` | `– (secret: set in .env)` |  |
| `LLM_MODEL` | `"openai/gpt-oss-20b"` |  |
| `LLM_PROVIDER` | `"openai"` |  |
| `LLM_JSON_RETRIES` | `3` | openai (any OpenAI-compatible API), anthropic, google_genai, groq, ... |
| `LLM_TIMEOUT_S` | `90` | extra attempts when the reply is not valid JSON for the schema |
| `LLM_MAX_RETRIES` | `1` | Quick retries inside one AI call (a dropped connection). Longer outages are retried by the worker (WORKER_MAX_ATTEMPTS), so keep this small. |
| `LLM_MAX_INPUT_CHARS` | `30_000` |  |
| `LLM_MAX_OUTPUT_TOKENS` | `16_000` | Cap on the AI's answer. A cut-off answer is retried once with "shorter", then reported as "too many people in one document" (no 3 x 3 retries). None = provider default. |
| `LLM_FALLBACK_MODEL` | `None` | long documents are cut to this before the LLM Fallback model: asked (instead of failing the job) when the main model cannot answer (provider down, rate limit, timeout, API error) or never returns valid JSON. Empty LLM_FALLBACK_MODEL = no fallback. Provider, base URL and key default to the main ones, but only where that is safe: the base URL only for the same provider, the key only for the same provider AND host (a key is never sent to a host it was not made for). |
| `LLM_FALLBACK_PROVIDER` | `None` |  |
| `LLM_FALLBACK_BASE_URL` | `None` |  |
| `LLM_FALLBACK_API_KEY` | `– (secret: set in .env)` |  |
| `CHUNKING_ENABLED` | `True` | Long documents (chunking.py): cut into overlapping pieces of at most CHUNK_TARGET_CHARS characters and CHUNK_PEOPLE new people, each piece starting CHUNK_OVERLAP_CHARS before the previous one ended. One AI call per piece (at most CHUNK_PARALLEL at a time; a failed piece retried CHUNK_PIECE_RETRIES times on its own), answers combined, then matching and rules once. Shorter documents: one call. |
| `CHUNK_TARGET_CHARS` | `12_000` |  |
| `CHUNK_OVERLAP_CHARS` | `1_500` |  |
| `CHUNK_PEOPLE` | `15` | each person: ~200 answer tokens |
| `CHUNK_MAX_PARTS` | `40` | more = document_too_large |
| `CHUNK_PARALLEL` | `2` |  |
| `CHUNK_PIECE_RETRIES` | `2` |  |

## Vision read: photos and scanned timesheets (OFF by default)

| Setting | Default | What it does |
|---|---|---|
| `VISION_ENABLED` | `False` | Photos and PDFs without a text layer are read by a vision-language model (e.g. Gemma 4 on Ollama, any OpenAI-compatible endpoint) instead of Docling + RapidOCR, which reads handwriting poorly. One call per page returns the kind of writing (printed / handwritten / mixed) and the transcription. Typed documents are never sent. When on, the page images go to VISION_BASE_URL: no default host, so nothing leaves this machine until someone sets one. ollama.com is a hosted (third-party) service. |
| `VISION_BASE_URL` | `None` | https://ollama.com/v1, or http://gpu-host:11434/v1 |
| `VISION_API_KEY` | `– (secret: set in .env)` | Ollama Cloud needs one; self-hosted usually not |
| `VISION_MODEL` | `None` | exactly as the server lists it, e.g. gemma4:31b-cloud |
| `VISION_PROVIDER` | `"openai"` | LangChain provider; "openai" = any compatible API |
| `VISION_TIMEOUT_S` | `120` | per page |
| `VISION_MAX_RETRIES` | `2` | quick retries per call |
| `VISION_MAX_OUTPUT_TOKENS` | `8000` |  |
| `VISION_MAX_PAGES` | `6` | pages read per document |
| `VISION_IMAGE_MAX_SIDE` | `2048` | Pages are shrunk (never enlarged) to this longest side (and about 2.5 MP). |
| `VISION_MIN_CONFIDENCE` | `0.8` | A page classified with less confidence than this counts as "uncertain". |

## Review

| Setting | Default | What it does |
|---|---|---|
| `AUTO_APPROVE_ENABLED` | `True` |  |
| `AUTO_APPROVE_MIN_CONFIDENCE` | `0.85` |  |

## Email listener (IMAP): only the core-email container uses these

| Setting | Default | What it does |
|---|---|---|
| `EMAIL_ENABLED` | `False` |  |
| `IMAP_HOST` | `None` | imap.gmail.com |
| `IMAP_PORT` | `993` |  |
| `IMAP_USER` | `None` |  |
| `IMAP_PASSWORD` | `– (secret: set in .env)` | Gmail: an App Password, never the real one |
| `IMAP_FOLDER` | `"INBOX"` |  |
| `EMAIL_IDLE_TIMEOUT` | `120` | Seconds in one IDLE round before ending it and checking again. Kept short: an idle connection can be closed silently by a router / NAT / Docker Desktop well before Gmail's own ~29 min limit, and the next round would then fail with SSLEOFError. |
| `IMAP_TIMEOUT_S` | `60` | any other IMAP call (fetch, logout) gives up after this |
| `EMAIL_START_FROM` | `"new"` | first run: only new mail, or recent too |
| `EMAIL_BACKFILL_DAYS` | `2` |  |
| `EMAIL_REQUIRE_SENDER_AUTH` | `True` | our mail server must have verified SPF/DKIM/DMARC |
| `EMAIL_MAX_ATTACHMENTS` | `20` |  |
| `EMAIL_MAX_INTAKE_FAILURES` | `3` | An email that fails to be saved this many times (not because the database or Redis is down) is recorded as failed and skipped, so it cannot block the inbox. |
| `IMAP_MARK_AS_READ` | `False` | Mark each email as read in the mailbox once it is saved (or ignored / already seen). Off: the listener never changes the mailbox. A skipped (broken) email is always left unread, so a person notices it. |

## "Open in Gmail" links (core-service API)

| Setting | Default | What it does |
|---|---|---|
| `MAILBOX_ACCOUNT` | `None` | The mailbox address, as in IMAP_USER (the API does not load the IMAP settings). Empty: no links are shown. |
| `MAILBOX_LINK_TEMPLATE` | `"https://mail.google.com/mail/?authuser={account}#search/rfc822msgid%3A{message_id}"` | {account} and {message_id} (URL-encoded, without < >) are filled in. |

## Worker retries (temporary failures: AI model down, database / Redis unreachable)

| Setting | Default | What it does |
|---|---|---|
| `WORKER_MAX_ATTEMPTS` | `3` | runs per job, including the first |
| `WORKER_RETRY_DELAY_SECONDS` | `60` | wait before the 2nd run; x4 for each run after |
| `WORKER_STALE_AFTER_SECONDS` | `1800` | A job "processing" with no progress for this long is treated as abandoned (the worker died): another worker may take it over. Progress = every state / document. |
| `WORKER_JOB_TIMEOUT_SECONDS` | `1500` | One job may run this long; then it stops with "took too long" (no retry). |
| `WORKER_HARD_TIME_LIMIT_SECONDS` | `1620` | Celery kills a job that is still running this long after it started (a backstop if the job is stuck in code that cannot be interrupted). |
| `BROKER_VISIBILITY_TIMEOUT_SECONDS` | `3600` | Redis hands an unfinished job to another worker after this long. Must be longer than any job can run, or a running job would be started a second time. |

## Attachment classifier (Jev by TypeSafe): optional, OFF by default

| Setting | Default | What it does |
|---|---|---|
| `CLASSIFIER_ENABLED` | `False` | Asks "is this document a timesheet?" after reading and before the AI extraction. Extraction is skipped ONLY when the label is not timesheet AND P(timesheet) is below CLASSIFIER_SKIP_BELOW. Errors, timeouts, unknown answers and manual reprocessing always continue as before. Shadow mode only logs what it would do. |
| `CLASSIFIER_SHADOW_ONLY` | `True` |  |
| `CLASSIFIER_SKIP_BELOW` | `0.2` |  |
| `CLASSIFIER_TIMEOUT_S` | `10` |  |
| `CLASSIFIER_MAX_CHARS` | `8000` | start of the text only |
| `JEV_API_KEY` | `– (secret: set in .env)` | in .env only |
| `JEV_MODEL` | `"jev-1.13.0"` | pinned: "latest" could change answers silently |
| `JEV_URL` | `"https://api.typesafe.ai/v1/systemone"` |  |

## OpenTelemetry: logs and traces (src/observability)

| Setting | Default | What it does |
|---|---|---|
| `OTEL_ENABLED` | `False` | Logs always go through OpenTelemetry (observability/logging/setup.py). OTEL_ENABLED turns on traces, so every log line written inside a request or job carries its trace id (the same id is saved on each step-log row). Nothing leaves the process unless OTEL_EXPORTER_OTLP_ENDPOINT is set (an OpenTelemetry Collector, Grafana, SigNoz...). |
| `OTEL_SERVICE_NAME` | `"core-service"` | compose sets core-worker / core-email |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `None` | e.g. http://otel-collector:4318 |
| `OTEL_LOGS_CONSOLE` | `True` | log records on stdout |
| `OTEL_LOGS_FORMAT` | `"text"` | stdout format: "text" = a normal log line per record, "json" = one JSON object per line (for a log shipper reading the container output) |
| `OTEL_SAMPLE_RATIO` | `1.0` | share of traces kept |

## Sweeper (Celery beat): re-queue work that was lost

| Setting | Default | What it does |
|---|---|---|
| `SWEEPER_INTERVAL_SECONDS` | `120` | how often it looks |
| `SWEEPER_GRACE_SECONDS` | `600` | "received" (or a retry overdue) this long = lost |
| `DASHBOARD_POLL_SECONDS` | `30` | refresh even without a change message |
| `DASHBOARD_HEARTBEAT_SECONDS` | `15` | keeps proxies from closing an idle stream |
| `DASHBOARD_MAX_STREAMS_PER_USER` | `5` | per API process (open tabs) |
