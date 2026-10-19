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
    redis_url: str = "redis://127.0.0.1:6379/0"

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
