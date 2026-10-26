# core-service: runbook

## Start

```powershell
cd backend ; docker compose up -d          # everything (API, worker, email listener, nginx)
docker compose logs -f core-worker         # follow the worker
```

Locally without Docker (needs PostgreSQL and Redis):

```powershell
cd backend\core-service
uv run uvicorn src.main:app --reload --port 8002
uv run celery -A src.control.workers.celery_app worker -Q timesheets -l info
uv run python -m src.control.workers.email_listener
```

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
| Submissions stay "received" | the worker is not running, or cannot reach Redis: `docker compose logs core-worker` |
| "The AI model did not answer" | LLM_BASE_URL / LLM_API_KEY / LLM_MODEL wrong, or the provider is down; the job retries by itself (WORKER_MAX_ATTEMPTS) |
| Every request is 429 | more than RATE_LIMIT requests a minute from one IP (an office shares one); raise RATE_LIMIT |
| 401 on every call | JWT_PUBLIC_KEY_PATH does not match auth-service's private key |
| Photos read badly | VISION_ENABLED=false: they are read by OCR; see the README's vision section |
| `document_too_large` flags | the file has more pages / sheets / parts than allowed (MAX_PAGES, MAX_SHEETS, CHUNK_MAX_PARTS) |

Reset test data: the `reset-test-data.ps1` script (asks before deleting timesheets and
companies).
