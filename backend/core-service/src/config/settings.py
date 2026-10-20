from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    docs_enabled: bool = True

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
    email_idle_timeout: int = 300  # seconds in IDLE before a safety re-check
    email_start_from: Literal["new", "backfill"] = "new"  # first run: only new mail, or recent too
    email_backfill_days: int = 2
    email_require_sender_auth: bool = True  # our mail server must have verified SPF/DKIM/DMARC
    email_max_attachments: int = 20
    # An email that fails to be saved this many times (not because the database or
    # Redis is down) is recorded as failed and skipped, so it cannot block the inbox.
    email_max_intake_failures: int = 3

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

    # --- tracing (OpenTelemetry) ---
    # Off by default. In docker compose it is on and traces go to Jaeger
    # (UI at http://localhost:16686). The state log and step log in PostgreSQL stay the
    # record of what happened; traces show timings across API -> queue -> worker.
    otel_enabled: bool = False
    otel_service_name: str = "core-service"  # compose sets core-worker / core-email
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"  # OTLP over HTTP
    otel_sample_ratio: float = Field(default=1.0, ge=0, le=1)  # share of traces kept

    # --- sweeper (Celery beat): re-queue work that was lost ---
    sweeper_interval_seconds: int = 120  # how often it looks
    sweeper_grace_seconds: int = 600  # "received" (or a retry overdue) this long = lost

    @model_validator(mode="after")
    def check_classifier(self) -> "Settings":
        key = self.jev_api_key.get_secret_value().strip() if self.jev_api_key else ""
        if self.classifier_enabled and not key:  # an empty JEV_API_KEY= counts as missing
            raise ValueError("CLASSIFIER_ENABLED=true needs JEV_API_KEY in .env")
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
