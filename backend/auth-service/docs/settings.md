# auth-service: settings

Every setting is read from the environment (or the service's `.env`) by
`src/config/settings.py`; names are case-insensitive. Secrets have no default here: set
them in `.env` only (never committed). Generated from settings.py.

| Setting | Default | What it does |
|---|---|---|
| `APP_NAME` | `"auth-service"` |  |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Browser apps allowed to call this API (the frontend). In .env as JSON, e.g. CORS_ORIGINS=["https://timesheets.example.com"]. Use the same host name the browser uses (localhost and 127.0.0.1 are different origins). |
| `ENVIRONMENT` | `"local"` |  |
| `DOCS_ENABLED` | `False` | API docs (/docs, /redoc, /openapi.json). Off by default so a deployed service does not publish its full API map; DOCS_ENABLED=true in .env for local development. |
| `AUTH_PUBLIC_PATHS` | `["/health", "/health/db", "/auth/login", "/auth/refresh", "/auth/logout", "/auth/forgot-password", "/auth/reset-password"]` | Paths anyone may call without a token (the auth middleware denies everything else). The API docs are added automatically when DOCS_ENABLED=true; OPTIONS always passes. |

## Rate limiting (src/api/middleware/rate_limit.py)

| Setting | Default | What it does |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `True` | One limit for every endpoint: RATE_LIMIT requests ("requests/window_seconds") per client IP, shared with core-service (same Redis counter). The IP is the X-Real-IP header nginx sets (else the socket address). Health checks are never counted. |
| `RATE_LIMIT_FAIL_OPEN` | `True` | Redis down: let requests through (False: 503) |
| `RATE_LIMIT` | `"100/60"` |  |
| `RATE_LIMIT_EXEMPT_PATHS` | `["/health", "/health/db"]` |  |

## Bulk import of users (POST /users/import)

| Setting | Default | What it does |
|---|---|---|
| `MAX_IMPORT_MB` | `5` | largest file accepted |
| `MAX_IMPORT_ROWS` | `5000` | data rows per file |
| `IMPORT_REPORT_ROWS` | `200` | row details in the reply |
| `MAX_USER_IMPORT_ROWS` | `200` | Users only: each new password is hashed with Argon2 (~0.15 s each, on purpose), so a file of users is capped lower to keep one import well under a minute. |
| `MAX_UNCOMPRESSED_MB` | `100` | XLSX files are zip packages: refuse ones that unpack to more than this, or that are compressed more than MAX_COMPRESSION_RATIO to 1 (zip bombs). |
| `MAX_COMPRESSION_RATIO` | `100` |  |
| `DATABASE_URL` | `"postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/timesheet_db"` | postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB_NAME |
| `DB_POOL_SIZE` | `10` |  |
| `DB_MAX_OVERFLOW` | `10` |  |
| `DB_ECHO` | `False` |  |

## JWT (RS256: sign with the private key, verify with the public key)

| Setting | Default | What it does |
|---|---|---|
| `JWT_PRIVATE_KEY_PATH` | `Path("keys/jwt_private.pem")` | auth-service only |
| `JWT_PUBLIC_KEY_PATH` | `Path( "keys/jwt_public.pem" )` |  |
| `JWT_ALGORITHM` | `"RS256"` |  |
| `JWT_ISSUER` | `"auth-service"` | "iss": who made the token |
| `JWT_AUDIENCE` | `"timesheet-api"` | "aud": who the token is for |
| `ACCESS_TOKEN_MINUTES` | `15` |  |
| `REFRESH_TOKEN_DAYS` | `7` |  |
| `OTP_SECRET` | `– (secret: set in .env)` | Secret for hashing password-reset codes (HMAC). No default on purpose. |

## Refresh-token cookie

| Setting | Default | What it does |
|---|---|---|
| `REFRESH_COOKIE_NAME` | `"refresh_token"` |  |
| `REFRESH_COOKIE_PATH` | `"/auth"` | the browser only sends it to /auth/* |
| `REFRESH_COOKIE_SECURE` | `True` | True in production (HTTPS). Set REFRESH_COOKIE_SECURE=false for local http. |

## Logs and traces (OpenTelemetry, src/observability)

| Setting | Default | What it does |
|---|---|---|
| `LOG_LEVEL` | `"INFO"` | Logs always go through OpenTelemetry (observability/logging/setup.py). OTEL_ENABLED turns on traces, so log lines written inside a request carry its trace id. Nothing leaves the process unless OTEL_EXPORTER_OTLP_ENDPOINT is set (an OpenTelemetry Collector). |
| `OTEL_ENABLED` | `False` |  |
| `OTEL_SERVICE_NAME` | `"auth-service"` |  |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `None` | e.g. http://otel-collector:4318 |
| `OTEL_LOGS_CONSOLE` | `True` | log records on stdout |
| `OTEL_LOGS_FORMAT` | `"text"` | stdout format: "text" = a normal log line per record, "json" = one JSON object per line (for a log shipper reading the container output) |
| `OTEL_SAMPLE_RATIO` | `1.0` |  |

## Redis (password-reset codes and lockouts)

| Setting | Default | What it does |
|---|---|---|
| `REDIS_URL` | `"redis://127.0.0.1:6379/0"` |  |

## SMTP (outgoing email)

| Setting | Default | What it does |
|---|---|---|
| `SMTP_HOST` | `"smtp.gmail.com"` |  |
| `SMTP_PORT` | `587` | 587 = STARTTLS, 465 = SSL |
| `SMTP_USERNAME` | `None` |  |
| `SMTP_PASSWORD` | `– (secret: set in .env)` |  |
| `SMTP_FROM_EMAIL` | `None` | defaults to smtp_username |
| `SMTP_FROM_NAME` | `"Timesheet Assistant"` |  |
| `SMTP_USE_SSL` | `False` | True for port 465 |
| `SMTP_STARTTLS` | `True` | True for port 587 |
| `SMTP_TIMEOUT_S` | `20` |  |

## Forgot / reset password

| Setting | Default | What it does |
|---|---|---|
| `OTP_TTL_MINUTES` | `10` | how long a code stays valid |
| `OTP_MAX_ATTEMPTS` | `3` | wrong codes allowed before the lockout |
| `OTP_LOCKOUT_MINUTES` | `30` |  |
| `OTP_RESEND_COOLDOWN_SECONDS` | `60` | wait between two "send code" requests |

## First super admin (seed)

| Setting | Default | What it does |
|---|---|---|
| `BOOTSTRAP_ADMIN_NAME` | `"Super Admin"` |  |
| `BOOTSTRAP_ADMIN_EMAIL` | `None` |  |
| `BOOTSTRAP_ADMIN_PASSWORD` | `– (secret: set in .env)` |  |
| `PRODUCT_NAME` | `"Timesheet Processing Assistant"` | Used in emails sent to users |
| `LOGIN_URL` | `"http://localhost:5173/login"` |  |

