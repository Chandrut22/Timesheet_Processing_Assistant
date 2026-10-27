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

## Build and deploy

Run from the repo root, in PowerShell (`;` separates commands). Migrations run by
themselves: core-service runs `alembic upgrade head` before it starts, and the worker waits
until core-service is healthy.

```powershell
# 1. Frontend: install, check, build (the nginx image builds it again inside Docker)
cd frontend ; npm ci ; npm run typecheck ; npm run lint ; npm test ; npm run build ; cd ..

# 2. Backend checks (each service)
cd backend\core-service ; uv sync ; uv run ruff check . ; uv run ruff format --check . ; uv run mypy src tests ; uv run pytest ; cd ..\..

# 3. Build the images and start everything
cd backend ; docker compose build ; docker compose up -d

# 4. Watch the migration and the services come up
docker compose logs -f core-service        # "Running upgrade ... -> c4d8a2e6f0b3" then "Uvicorn running"
docker compose ps                          # every service "running" / "healthy"
docker compose exec core-service alembic current   # c4d8a2e6f0b3 (head)
```

Only one part changed? Rebuild just that: `docker compose up -d --build core-service
core-worker core-email` (backend; one image for all three) or `docker compose up -d
--build nginx` (frontend). Production (no override file):
`docker compose -f docker-compose.yml up -d --build`.

## Checks

```powershell
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src tests ; uv run pytest
```

or `make check` where `make` is installed (Git Bash, WSL). Integration tests need a
throw-away database: `TEST_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:5433/timesheet_test`
(its name must contain "test"; run `alembic upgrade head` on it first). The "Check mail
now" tests also need `TEST_REDIS_URL`, a Redis database other than 0 (they delete the
listener's keys), with REDIS_PASSWORD from backend/.env; without it they are skipped:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://postgres:PASSWORD@127.0.0.1:5433/timesheet_test" ; uv run alembic upgrade head
$env:TEST_DATABASE_URL=$env:DATABASE_URL ; $env:TEST_REDIS_URL="redis://:REDIS_PASSWORD@127.0.0.1:6380/15"
uv run pytest ; Remove-Item Env:DATABASE_URL, Env:TEST_DATABASE_URL, Env:TEST_REDIS_URL
```

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
| Migration fails with "permission denied to create extension" | the database user may not create extensions: run `CREATE EXTENSION pg_trgm; CREATE EXTENSION unaccent;` once as a superuser (Cloud SQL: the `cloudsqlsuperuser` role), then restart core-service |
| Every request is 429 | more than RATE_LIMIT requests a minute from one IP (an office shares one); raise RATE_LIMIT |
| 401 on every call | JWT_PUBLIC_KEY_PATH does not match auth-service's private key |
| Photos read badly | VISION_ENABLED=false: they are read by OCR; see the README's vision section |
| `document_too_large` flags | the file has more pages / sheets / parts than allowed (MAX_PAGES, MAX_SHEETS, CHUNK_MAX_PARTS) |

Reset test data: the `reset-test-data.ps1` script (asks before deleting timesheets and
companies).
