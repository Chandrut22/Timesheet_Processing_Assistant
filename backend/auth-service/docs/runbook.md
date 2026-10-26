# auth-service: runbook

## Start

```powershell
cd backend ; docker compose up -d auth-service
```

Locally without Docker (needs PostgreSQL and Redis):

```powershell
cd backend\auth-service
uv run uvicorn src.main:app --reload --port 8001
```

On start the service creates the two roles and, if no admin exists, the first admin from
BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD (core/services/seed_service.py).

Keys: `uv run python scripts/generate_keys.py` writes the RS256 key pair; core-service
needs the public key only. Never commit `keys/` or `.env`.

## Checks

```powershell
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src tests ; uv run pytest
```

or `make check` where `make` is installed (Git Bash, WSL). Integration tests need a
throw-away database: `TEST_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:5433/timesheet_test`
(its name must contain "test"; run `alembic upgrade head` on it first).

## Database migrations

```powershell
uv run alembic upgrade head                      # apply
uv run alembic revision --autogenerate -m "..."  # after changing a model
uv run alembic check                             # models and database agree
uv run alembic downgrade -1                      # undo the last one
```

## Common problems

| Symptom | Cause / fix |
|---|---|
| Sign-in lost on reload | over plain http: set REFRESH_COOKIE_SECURE=false |
| "Too many requests" on login | more than RATE_LIMIT requests a minute from one IP (shared with core-service) |
| Reset code never arrives | SMTP_* settings, or the email went to spam; the code is valid for OTP_TTL_MINUTES |
| "Too many attempts" on reset | OTP_MAX_ATTEMPTS wrong codes: locked for OTP_LOCKOUT_MINUTES |
