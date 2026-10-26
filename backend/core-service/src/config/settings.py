from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "core-service"

    # Browser apps allowed to call this API (the frontend). In .env as JSON, e.g.
    # CORS_ORIGINS=["https://timesheets.example.com"]. Use the same host name the
    # browser uses (localhost and 127.0.0.1 are different origins).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    environment: str = "dev"
    log_level: str = "INFO"
    # API docs (/docs, /openapi.json). Off by default so a deployed service does not
    # publish its full API map; DOCS_ENABLED=true in .env for local development.
    docs_enabled: bool = False
    # Paths anyone may call without a token (the auth middleware denies everything else).
    # The API docs are added automatically when DOCS_ENABLED=true; OPTIONS always passes.
    auth_public_paths: list[str] = ["/health", "/health/db", "/health/redis"]

    # --- rate limiting (src/api/middleware/rate_limit.py) ---
    # One limit for every endpoint: RATE_LIMIT requests ("requests/window_seconds") per
    # client IP, shared with auth-service (same Redis counter). The IP is the X-Real-IP header
    # nginx sets (else the socket address). Health checks are never counted.
    rate_limit_enabled: bool = True
    rate_limit_fail_open: bool = True  # Redis down: let requests through (False: 503)
    rate_limit: str = Field(default="100/60", pattern=r"^\d+/\d+$")
    rate_limit_exempt_paths: list[str] = ["/health", "/health/db", "/health/redis"]

    # --- database: shared timesheet_db, this service owns the "core" schema ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/timesheet_db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- redis: shared db 0, every key starts with "core:" ---
    redis_url: str = "redis://127.0.0.1:6380/0"
    redis_prefix: str = "core"

    # --- JWT: core only VERIFIES tokens, so it needs only the PUBLIC key ---
    jwt_public_key_path: Path = Path("keys/jwt_public.pem")
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "auth-service"
    jwt_audience: str = "timesheet-api"

    # --- uploads ---
    max_upload_mb: int = 15
    max_files_per_upload: int = 10
    # Uploaded / emailed files wait here (one file per document) until the worker has
    # read them; then they are deleted. A shared Docker volume in compose. Never in Redis.
    upload_dir: Path = Path("data/uploads")
    upload_buffer_ttl_hours: int = 72  # a file not read by then is deleted (sweeper)
    # DOCX / XLSX are zip packages: refuse one that unpacks to more than this, or that is
    # compressed more than MAX_COMPRESSION_RATIO to 1 (how zip bombs look). Checked from
    # the zip's directory before any reader opens the file (src/utils/file_checks.py).
    max_uncompressed_mb: int = Field(default=100, ge=1)
    max_compression_ratio: int = Field(default=100, ge=10)
    # Bulk import of employees / companies / holidays (CSV or XLSX, admins only).
    max_import_mb: int = Field(default=5, ge=1, le=50)
    max_import_rows: int = Field(default=5000, ge=1)
    import_report_rows: int = Field(default=200, ge=10)  # row details in the response
    # Big files: counted BEFORE reading (reading is the slow part, and the AI only sees
    # the first LLM_MAX_INPUT_CHARS anyway). Hidden and empty Excel sheets are never read.
    max_pages: int = Field(default=50, ge=1)  # PDF pages read
    max_sheets: int = Field(default=30, ge=1)  # Excel sheets (with data) read
    # partial: read the first MAX_PAGES / MAX_SHEETS and flag document_too_large
    # refuse:  do not read the file; "split it and send it again"
    large_document_mode: Literal["partial", "refuse"] = "partial"

    # --- LLM: any OpenAI-compatible API (Groq, OpenRouter, OpenAI, Ollama, vLLM) ---
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = "openai/gpt-oss-20b"
    llm_provider: str = "openai"
    # openai (any OpenAI-compatible API), anthropic, google_genai, groq, ...
    llm_json_retries: int = 3
    # extra attempts when the reply is not valid JSON for the schema
    llm_timeout_s: float = 90
    # Quick retries inside one AI call (a dropped connection). Longer outages are
    # retried by the worker (WORKER_MAX_ATTEMPTS), so keep this small.
    llm_max_retries: int = 1
    llm_max_input_chars: int = 30_000
    # Cap on the AI's answer. A cut-off answer is retried once with "shorter", then
    # reported as "too many people in one document" (no 3 x 3 retries). None = provider default.
    llm_max_output_tokens: int | None = 16_000
    # long documents are cut to this before the LLM
    # Fallback model: asked (instead of failing the job) when the main model cannot answer
    # (provider down, rate limit, timeout, API error) or never returns valid JSON.
    # Empty LLM_FALLBACK_MODEL = no fallback. Provider, base URL and key default to the main
    # ones, but only where that is safe: the base URL only for the same provider, the key
    # only for the same provider AND host (a key is never sent to a host it was not made for).
    llm_fallback_model: str | None = None
    llm_fallback_provider: str | None = None
    llm_fallback_base_url: str | None = None
    llm_fallback_api_key: SecretStr | None = None
    # Long documents (chunking.py): cut into overlapping pieces of at most
    # CHUNK_TARGET_CHARS characters and CHUNK_PEOPLE new people, each piece starting
    # CHUNK_OVERLAP_CHARS before the previous one ended. One AI call per piece (at most
    # CHUNK_PARALLEL at a time; a failed piece retried CHUNK_PIECE_RETRIES times on its
    # own), answers combined, then matching and rules once. Shorter documents: one call.
    chunking_enabled: bool = True
    chunk_target_chars: int = Field(default=12_000, ge=2_000, le=100_000)
    chunk_overlap_chars: int = Field(default=1_500, ge=0, le=20_000)
    chunk_people: int = Field(default=15, ge=1, le=100)  # each person: ~200 answer tokens
    chunk_max_parts: int = Field(default=40, ge=1, le=200)  # more = document_too_large
    chunk_parallel: int = Field(default=2, ge=1, le=8)
    chunk_piece_retries: int = Field(default=2, ge=0, le=5)

    # --- vision read: photos and scanned timesheets (OFF by default) ---
    # Photos and PDFs without a text layer are read by a vision-language model (e.g. Gemma 4
    # on Ollama, any OpenAI-compatible endpoint) instead of Docling + RapidOCR, which reads
    # handwriting poorly. One call per page returns the kind of writing (printed /
    # handwritten / mixed) and the transcription. Typed documents are never sent. When on,
    # the page images go to VISION_BASE_URL: no default host, so nothing leaves this
    # machine until someone sets one. ollama.com is a hosted (third-party) service.
    vision_enabled: bool = False
    vision_base_url: str | None = None  # https://ollama.com/v1, or http://gpu-host:11434/v1
    vision_api_key: SecretStr | None = None  # Ollama Cloud needs one; self-hosted usually not
    vision_model: str | None = None  # exactly as the server lists it, e.g. gemma4:31b-cloud
    vision_provider: str = "openai"  # LangChain provider; "openai" = any compatible API
    vision_timeout_s: float = Field(default=120, gt=0)  # per page
    vision_max_retries: int = Field(default=2, ge=0, le=5)  # quick retries per call
    vision_max_output_tokens: int = Field(default=8000, ge=256)
    vision_max_pages: int = Field(default=6, ge=1, le=50)  # pages read per document
    # Pages are shrunk (never enlarged) to this longest side (and about 2.5 MP).
    vision_image_max_side: int = Field(default=2048, ge=512, le=8192)
    # A page classified with less confidence than this counts as "uncertain".
    vision_min_confidence: float = Field(default=0.8, ge=0, le=1)

    # --- review ---
    auto_approve_enabled: bool = True
    auto_approve_min_confidence: float = 0.85

    # --- email listener (IMAP): only the core-email container uses these ---
    email_enabled: bool = False
    imap_host: str | None = None  # imap.gmail.com
    imap_port: int = 993
    imap_user: str | None = None
    imap_password: SecretStr | None = None  # Gmail: an App Password, never the real one
    imap_folder: str = "INBOX"
    # Seconds in one IDLE round before ending it and checking again. Kept short: an idle
    # connection can be closed silently by a router / NAT / Docker Desktop well before
    # Gmail's own ~29 min limit, and the next round would then fail with SSLEOFError.
    email_idle_timeout: int = 120
    imap_timeout_s: int = 60  # any other IMAP call (fetch, logout) gives up after this
    email_start_from: Literal["new", "backfill"] = "new"  # first run: only new mail, or recent too
    email_backfill_days: int = 2
    email_require_sender_auth: bool = True  # our mail server must have verified SPF/DKIM/DMARC
    email_max_attachments: int = 20
    # An email that fails to be saved this many times (not because the database or
    # Redis is down) is recorded as failed and skipped, so it cannot block the inbox.
    email_max_intake_failures: int = 3
    # Mark each email as read in the mailbox once it is saved (or ignored / already
    # seen). Off: the listener never changes the mailbox. A skipped (broken) email is
    # always left unread, so a person notices it.
    imap_mark_as_read: bool = False

    # --- "Open in Gmail" links (core-service API) ---
    # The mailbox address, as in IMAP_USER (the API does not load the IMAP settings).
    # Empty: no links are shown.
    mailbox_account: str | None = None
    # {account} and {message_id} (URL-encoded, without < >) are filled in.
    mailbox_link_template: str = (
        "https://mail.google.com/mail/?authuser={account}#search/rfc822msgid%3A{message_id}"
    )

    # --- worker retries (temporary failures: AI model down, database / Redis unreachable) ---
    worker_max_attempts: int = 3  # runs per job, including the first
    worker_retry_delay_seconds: int = 60  # wait before the 2nd run; x4 for each run after
    # A job "processing" with no progress for this long is treated as abandoned (the
    # worker died): another worker may take it over. Progress = every state / document.
    worker_stale_after_seconds: int = 1800
    # One job may run this long; then it stops with "took too long" (no retry).
    worker_job_timeout_seconds: int = 1500
    # Celery kills a job that is still running this long after it started (a backstop if
    # the job is stuck in code that cannot be interrupted).
    worker_hard_time_limit_seconds: int = 1620
    # Redis hands an unfinished job to another worker after this long. Must be longer
    # than any job can run, or a running job would be started a second time.
    broker_visibility_timeout_seconds: int = 3600

    # --- attachment classifier (Jev by TypeSafe): optional, OFF by default ---
    # Asks "is this document a timesheet?" after reading and before the AI extraction.
    # Extraction is skipped ONLY when the label is not timesheet AND P(timesheet) is
    # below CLASSIFIER_SKIP_BELOW. Errors, timeouts, unknown answers and manual
    # reprocessing always continue as before. Shadow mode only logs what it would do.
    classifier_enabled: bool = False
    classifier_shadow_only: bool = True
    classifier_skip_below: float = Field(default=0.2, ge=0, le=1)
    classifier_timeout_s: float = Field(default=10, gt=0, le=60)
    classifier_max_chars: int = Field(default=8000, ge=500, le=32000)  # start of the text only
    jev_api_key: SecretStr | None = None  # in .env only
    jev_model: str = "jev-1.13.0"  # pinned: "latest" could change answers silently
    jev_url: str = "https://api.typesafe.ai/v1/systemone"

    # --- OpenTelemetry: logs and traces (src/observability) ---
    # Logs always go through OpenTelemetry (observability/logging/setup.py). OTEL_ENABLED turns on
    # traces, so every log line written inside a request or job carries its trace id
    # (the same id is saved on each step-log row). Nothing leaves the process unless
    # OTEL_EXPORTER_OTLP_ENDPOINT is set (an OpenTelemetry Collector, Grafana, SigNoz...).
    otel_enabled: bool = False
    otel_service_name: str = "core-service"  # compose sets core-worker / core-email
    otel_exporter_otlp_endpoint: str | None = None  # e.g. http://otel-collector:4318
    otel_logs_console: bool = True  # log records on stdout
    # stdout format: "text" = a normal log line per record, "json" = one JSON object
    # per line (for a log shipper reading the container output)
    otel_logs_format: Literal["text", "json"] = "text"
    otel_sample_ratio: float = Field(default=1.0, ge=0, le=1)  # share of traces kept

    # --- sweeper (Celery beat): re-queue work that was lost ---
    sweeper_interval_seconds: int = 120  # how often it looks
    sweeper_grace_seconds: int = 600  # "received" (or a retry overdue) this long = lost

    dashboard_poll_seconds: int = 30  # refresh even without a change message
    dashboard_heartbeat_seconds: int = 15  # keeps proxies from closing an idle stream
    dashboard_max_streams_per_user: int = 5  # per API process (open tabs)

    @field_validator(
        "llm_fallback_model",
        "llm_fallback_provider",
        "llm_fallback_base_url",
        "llm_fallback_api_key",
        "otel_exporter_otlp_endpoint",
        mode="before",
    )
    @classmethod
    def blank_fallback_is_unset(cls, value: object) -> object:
        """A blank line in .env (LLM_FALLBACK_MODEL=) means "not set"."""
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def llm_fallback_provider_effective(self) -> str:
        return self.llm_fallback_provider or self.llm_provider

    @property
    def llm_fallback_base_url_effective(self) -> str | None:
        if self.llm_fallback_base_url:
            return self.llm_fallback_base_url
        # The main base URL belongs to the main provider: not inherited across providers.
        same_provider = self.llm_fallback_provider_effective == self.llm_provider
        return self.llm_base_url if same_provider else None

    @property
    def llm_fallback_api_key_effective(self) -> SecretStr | None:
        if self.llm_fallback_api_key is not None:
            return self.llm_fallback_api_key
        # The main key only goes to the host and provider it was made for.
        same_provider = self.llm_fallback_provider_effective == self.llm_provider
        same_host = self.llm_fallback_base_url_effective == self.llm_base_url
        return self.llm_api_key if same_provider and same_host else None

    @model_validator(mode="after")
    def check_llm_fallback(self) -> "Settings":
        if self.llm_fallback_model is None:
            return self
        if self.llm_fallback_api_key_effective is None:
            raise ValueError(
                "LLM_FALLBACK_MODEL is set but there is no key for it: set "
                "LLM_FALLBACK_API_KEY (the main key is only reused for the same provider "
                "and base URL)"
            )
        same_as_main = (
            self.llm_fallback_model == self.llm_model
            and self.llm_fallback_provider_effective == self.llm_provider
            and self.llm_fallback_base_url_effective == self.llm_base_url
        )
        if same_as_main:
            raise ValueError(
                "LLM_FALLBACK_MODEL is the same model, provider and base URL as the main "
                "model: pick a different one, or leave it empty"
            )
        return self

    @model_validator(mode="after")
    def check_classifier(self) -> "Settings":
        key = self.jev_api_key.get_secret_value().strip() if self.jev_api_key else ""
        if self.classifier_enabled and not key:  # an empty JEV_API_KEY= counts as missing
            raise ValueError("CLASSIFIER_ENABLED=true needs JEV_API_KEY in .env")
        return self

    @model_validator(mode="after")
    def check_vision(self) -> "Settings":
        if not self.vision_enabled:
            return self
        if not (self.vision_base_url or "").strip() or not (self.vision_model or "").strip():
            raise ValueError("VISION_ENABLED=true needs VISION_BASE_URL and VISION_MODEL in .env")
        # One job must be able to read every page (one call each) and still extract.
        needed = int(self.vision_max_pages * self.vision_timeout_s) + 300
        if self.worker_job_timeout_seconds < needed:
            raise ValueError(
                f"VISION_MAX_PAGES x VISION_TIMEOUT_S needs WORKER_JOB_TIMEOUT_SECONDS of at "
                f"least {needed} (and the other WORKER_* / BROKER_* times above it)"
            )
        return self

    @model_validator(mode="after")
    def check_worker_times(self) -> "Settings":
        """A job must be stopped before it counts as abandoned or is handed out again."""
        times = (
            self.worker_job_timeout_seconds,
            self.worker_hard_time_limit_seconds,
            self.worker_stale_after_seconds,
            self.broker_visibility_timeout_seconds,
        )
        if list(times) != sorted(times) or len(set(times)) != len(times):
            raise ValueError(
                "Need WORKER_JOB_TIMEOUT_SECONDS < WORKER_HARD_TIME_LIMIT_SECONDS < "
                "WORKER_STALE_AFTER_SECONDS < BROKER_VISIBILITY_TIMEOUT_SECONDS"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
