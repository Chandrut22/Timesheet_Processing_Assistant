# core-service: architecture

The timesheet pipeline (email / upload -> read -> extract -> match -> rules -> review ->
payroll export) and its REST API. FastAPI for the API, a Celery worker for the
processing, an IMAP listener for email, PostgreSQL (schema `core`) and Redis.

## Folders

```
src/
├── api/
│   ├── rest/
│   │   ├── app.py            create_app(): lifespan, middleware, routers, error handlers
│   │   ├── dependencies.py   DB session, the caller, role checks, paging
│   │   └── routes/           health, sse (live dashboard), me, companies, employees,
│   │                         holidays, uploads, submissions, timesheets, audit, exports,
│   │                         dashboard, importing
│   └── middleware/           cors, logging (one line per request), metrics,
│                             error_handler, auth (verifies the token), rate_limit
├── core/
│   ├── exceptions/           AppError and friends: each knows its HTTP status
│   ├── rbac/                 the caller (Principal), roles, token verification
│   └── services/             business logic
│       ├── pipeline/         reading, classifying, extracting, matching, deciding, ...
│       ├── documents/        turning files into text (Docling, CSV/TXT, size limits,
│       │                     damaged / password-protected files)
│       └── importing/        bulk import of companies, employees, holidays
├── data/
│   ├── clients/              postgres, redis, upload_buffer (files on disk), dashboard_hooks
│   ├── models/postgres/      SQLAlchemy models (re-exported by data/models)
│   ├── repositories/         queries, one repository per table
│   ├── migrations/           Alembic
│   └── actor.py              who is acting (created_by / updated_by)
├── handlers/
│   ├── http_clients/         the LLM (llm.py), the vision model, the Jev classifier
│   └── email/                IMAP: fetching and parsing email
├── control/
│   ├── agents/               the extraction agent and its prompt
│   └── workers/              Celery app and tasks, the email listener, the sweeper
├── observability/            logging/ (OpenTelemetry logs), metrics/, tracing/
├── schemas/                  Pydantic request / response models
├── config/                   settings.py (every setting, see docs/settings.md)
├── constants/  utils/  tools/ (evaluation scripts for the classifier and vision)
└── main.py                   entry point: `uvicorn src.main:app`
```

Entry points: `uvicorn src.main:app` (API), `celery -A src.control.workers.celery_app
worker` (processing), `python -m src.control.workers.email_listener` (email).

## Layers

```
api  ->  core / control  ->  handlers / data
         (schemas, config, constants, utils, observability: used by every layer)
```

A layer only imports the layers below it. `tests/unit/test_architecture.py` fails the
build when an import goes the wrong way:

| Layer | Never imports |
|---|---|
| `data` | `api`, `core`, `control`, `handlers` |
| `handlers` | `api`, `control` |
| `core` | `api` |
| `control` | `api` |

Old Alembic migrations are exempt: a migration is never edited after it has run.

## A request

CORS -> request log -> metrics -> auth (token) -> rate limit (100/min per IP) -> route
-> service (core) -> repository (data) -> PostgreSQL. Errors raised as `AppError`
become `{"detail", "code"}` JSON in `api/middleware/error_handler.py`.

## Observability

Logs, traces and metrics all go through OpenTelemetry: logs on stdout (text by default),
and everything to an OpenTelemetry Collector when `OTEL_ENABLED` and
`OTEL_EXPORTER_OTLP_ENDPOINT` are set. Metrics: `http.server.requests`,
`http.server.duration`, `http.server.active_requests`, `timesheet.extracted`,
`timesheet.submissions_failed`.
