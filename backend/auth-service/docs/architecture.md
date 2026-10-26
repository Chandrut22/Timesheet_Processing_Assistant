# auth-service: architecture

Users, roles and sign-in: issues the RS256 access tokens core-service verifies, the
refresh cookie, password reset by 6-digit code, and user administration (with bulk
import). FastAPI, PostgreSQL (schema `auth`) and Redis.

## Folders

```
src/
├── api/
│   ├── rest/
│   │   ├── app.py            create_app(): lifespan, middleware, routers, error handlers
│   │   ├── dependencies.py   DB session, the current user, role checks
│   │   └── routes/           health, auth (login, refresh, logout, me, passwords), users
│   └── middleware/           cors, logging (one line per request), metrics,
│                             error_handler, auth (verifies the token), rate_limit
├── core/
│   ├── exceptions/           AppError and friends: each knows its HTTP status
│   ├── security.py           password hashing (Argon2), token signing and checking
│   └── services/             auth, users, password reset, email, seed (roles, first admin),
│                             importing/ (bulk import of users)
├── data/
│   ├── clients/              postgres, redis
│   ├── models/postgres/      SQLAlchemy models: User, Role (re-exported by data/models)
│   ├── repositories/         user_repository
│   ├── migrations/           Alembic
│   └── actor.py              who is acting (created_by / updated_by)
├── observability/            logging/ (OpenTelemetry logs), metrics/, tracing/
├── schemas/  config/  constants/  utils/
└── main.py                   entry point: `uvicorn src.main:app`
```

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

CORS -> request log -> metrics -> auth (token, except public paths) -> rate limit
(100/min per IP, shared with core-service) -> route -> service -> repository -> PostgreSQL.

## Observability

Logs, traces and metrics through OpenTelemetry (see core-service). Metrics:
`http.server.requests`, `http.server.duration`, `http.server.active_requests`,
`auth.logins` (by result: success / failed).
