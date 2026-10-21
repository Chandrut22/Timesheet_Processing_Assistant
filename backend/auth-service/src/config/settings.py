from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (and .env when present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "auth-service"

    # Browser apps allowed to call this API (the frontend). In .env as JSON, e.g.
    # CORS_ORIGINS=["https://timesheets.example.com"]. Use the same host name the
    # browser uses (localhost and 127.0.0.1 are different origins).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    environment: str = "local"
    # API docs (/docs, /redoc, /openapi.json). Off by default so a deployed service does
    # not publish its full API map; DOCS_ENABLED=true in .env for local development.
    docs_enabled: bool = False
    # Paths anyone may call without a token (the auth middleware denies everything else).
    # The API docs are added automatically when DOCS_ENABLED=true; OPTIONS always passes.
    auth_public_paths: list[str] = [
        "/health",
        "/health/db",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/forgot-password",
        "/auth/reset-password",
    ]

    # --- rate limiting (src/api/middleware/rate_limit.py) ---
    # "requests/window_seconds" per route class. strict = sign-in, refresh and password
    # endpoints, always per IP; the others per signed-in user (or per IP when anonymous).
    rate_limit_enabled: bool = True
    rate_limit_fail_open: bool = True  # Redis down: let requests through (False: 503)
    rate_limit_strict: str = Field(default="10/60", pattern=r"^\d+/\d+$")
    rate_limit_upload: str = Field(default="20/60", pattern=r"^\d+/\d+$")
    rate_limit_default: str = Field(default="300/60", pattern=r"^\d+/\d+$")
    rate_limit_exempt_paths: list[str] = ["/health", "/health/db"]
    # How many proxies in front of the API we trust to write X-Forwarded-For (nginx = 1).
    # 0 = always use the socket address (set 0 when clients reach the API directly).
    trusted_proxy_hops: int = Field(default=1, ge=0, le=5)

    # --- Bulk import of users (POST /users/import) ---------------------------
    max_import_mb: int = Field(default=5, ge=1, le=50)  # largest file accepted
    max_import_rows: int = Field(default=5000, ge=1)  # data rows per file
    import_report_rows: int = Field(default=200, ge=1)  # row details in the reply
    # Users only: each new password is hashed with Argon2 (~0.15 s each, on purpose),
    # so a file of users is capped lower to keep one import well under a minute.
    max_user_import_rows: int = Field(default=200, ge=1)
    # XLSX files are zip packages: refuse ones that unpack to more than this, or that
    # are compressed more than MAX_COMPRESSION_RATIO to 1 (zip bombs).
    max_uncompressed_mb: int = Field(default=100, ge=1)
    max_compression_ratio: int = Field(default=100, ge=10)

    # postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB_NAME
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/timesheet_db"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- JWT (RS256: sign with the private key, verify with the public key) --
    jwt_private_key_path: Path = Path("keys/jwt_private.pem")  # auth-service only
    jwt_public_key_path: Path = Path(
        "keys/jwt_public.pem"
    )  # shared with other services
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "auth-service"  # "iss": who made the token
    jwt_audience: str = "timesheet-api"  # "aud": who the token is for
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Secret for hashing password-reset codes (HMAC). No default on purpose.
    otp_secret: SecretStr

    # --- Refresh-token cookie ------------------------------------------------
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_path: str = "/auth"  # the browser only sends it to /auth/*
    # True in production (HTTPS). Set REFRESH_COOKIE_SECURE=false for local http.
    refresh_cookie_secure: bool = True

    # --- Tracing (OpenTelemetry) -----------------------------------------------
    # Off by default; on in docker compose (traces go to Jaeger, UI on port 16686).
    otel_enabled: bool = False
    otel_service_name: str = "auth-service"
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"  # OTLP over HTTP
    otel_sample_ratio: float = Field(default=1.0, ge=0, le=1)

    # --- Redis (password-reset codes and lockouts) ---------------------------
    redis_url: str = (
        "redis://127.0.0.1:6379/0"  # with a password: redis://:PASSWORD@host:port/0
    )

    # --- SMTP (outgoing email) -----------------------------------------------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # 587 = STARTTLS, 465 = SSL
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None  # defaults to smtp_username
    smtp_from_name: str = "Timesheet Assistant"
    smtp_use_ssl: bool = False  # True for port 465
    smtp_starttls: bool = True  # True for port 587
    smtp_timeout_s: int = 20

    # --- Forgot / reset password ---------------------------------------------
    otp_ttl_minutes: int = 10  # how long a code stays valid
    otp_max_attempts: int = 3  # wrong codes allowed before the lockout
    otp_lockout_minutes: int = 30
    otp_resend_cooldown_seconds: int = 60  # wait between two "send code" requests

    # --- First super admin (seed) ---------------------------------------------
    bootstrap_admin_name: str = "Super Admin"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None

    # Used in emails sent to users
    product_name: str = "Timesheet Processing Assistant"
    login_url: str = "http://localhost:5173/login"


settings = Settings()
