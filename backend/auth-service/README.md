# auth-service

Users, roles, sign-in and password reset.

Docs: [architecture](docs/architecture.md) (folders, layers, a request's path) ·
[settings](docs/settings.md) (every setting) · [runbook](docs/runbook.md) (start,
checks, migrations, common problems). Development commands: the `Makefile`
(`make check`, `make run`, `make migrate`) or the PowerShell commands in the runbook.

## Rate limit

One limit for every endpoint of both services: at most `RATE_LIMIT` requests (default
`100/60`, 100 per 60 seconds) per client IP (`src/api/middleware/rate_limit.py`, the same
file in auth-service and core-service).

- **Shared:** both services count in the same Redis counter (`rl:ip:<ip>:<window>`), so
  calls to `/auth/...` and `/api/...` from one IP add up to the same 100. Signed in or not,
  only the IP counts.
- **Sliding window:** the limit holds in any 60 seconds, not only per calendar minute.
- **Over the limit:** `429 {"detail": "Too many requests. Try again in N seconds.", "code":
  "rate_limited"}` with `Retry-After`. Every response carries `X-RateLimit-Limit`,
  `-Remaining` and `-Reset`.
- **Not counted:** health checks (`RATE_LIMIT_EXEMPT_PATHS`) and CORS preflights.
- **Client IP:** the `X-Real-IP` header nginx sets (`$remote_addr`, overwriting anything a
  browser sent); without it, the socket address. `X-Forwarded-For` is never read. Only
  nginx is reachable from outside (`docker-compose.override.yml` publishes the APIs on
  127.0.0.1 only, for development). If a load balancer is ever put in front of nginx,
  configure nginx's real-IP module (`set_real_ip_from`, `real_ip_header`) so
  `$remote_addr` is the browser again.
- **Redis down:** `RATE_LIMIT_FAIL_OPEN=true` (default) lets requests through and logs a
  warning; `false` answers 503 `rate_limit_unavailable`.
- **Settings:** `RATE_LIMIT_ENABLED`, `RATE_LIMIT`, `RATE_LIMIT_FAIL_OPEN`,
  `RATE_LIMIT_EXEMPT_PATHS`.
