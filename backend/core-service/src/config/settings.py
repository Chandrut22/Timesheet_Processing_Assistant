from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "core-service"
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
    upload_buffer_ttl_hours: int = 24  
    # how long uploaded bytes wait in Redis for the worker

    # --- LLM: any OpenAI-compatible API (Groq, OpenRouter, OpenAI, Ollama, vLLM) ---
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = "openai/gpt-oss-20b"
    llm_provider: str = "openai"  
    # openai (any OpenAI-compatible API), anthropic, google_genai, groq, ...
    llm_json_retries: int = 3  
    # extra attempts when the reply is not valid JSON for the schema
    llm_timeout_s: float = 90
    llm_max_input_chars: int = 30_000  
    # long documents are cut to this before the LLM


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
