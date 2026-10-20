# Timesheet Processing Assistant: frontend

React app for reviewers and admins. It works with the existing backend:
**auth-service** (port 8001) and **core-service** (port 8002).

Stack: React 19, Vite 8, TypeScript (strict), TanStack Router (file routes), TanStack Query v5, axios,
Tailwind v4 with shadcn-style components (Radix), react-hook-form and zod, date-fns, Vitest.

## Run it

```bash
# 1. Backend running, with the refresh cookie allowed over plain http:
#    auth-service/.env  ->  REFRESH_COOKIE_SECURE=false
docker compose up -d                # in the backend folder

# 2. Frontend
cd frontend
npm install                         # first time: then commit package-lock.json
npm run gen:api                     # regenerate API types from both /openapi.json files
npm run dev                         # http://localhost:5173
```

**Commit `package-lock.json`.** Versions in `package.json` use `^`, so without the lock file a fresh
`npm install` (or the Docker build) can pull newer versions than the ones you tested. Run `npm install` once,
commit the lock file, and use `npm ci` from then on. The Dockerfile uses `npm ci` when the lock file is there.

## Run the whole app in Docker

The `frontend` service builds this app and serves it with nginx on **http://localhost:8080**. nginx forwards
`/auth/*` and `/users/*` to auth-service and `/api/*` to core-service, the same rules as the dev proxy
(`nginx.conf`).

```powershell
cd backend
docker compose build frontend
docker compose up -d
..\frontend\test-frontend.ps1        # acceptance checks (asks for an admin login)
```

- **Lock file first:** the image runs `npm ci`, so `frontend/package-lock.json` must be committed. The
  build stops with a clear message if it's missing.
- **Plain http:** set `REFRESH_COOKIE_SECURE=false` in `auth-service/.env`, or sign-in won't survive a
  reload.
- **Trace links:** set `VITE_JAEGER_URL=http://localhost:16686` in `backend/.env` (or the shell), then
  rebuild with `docker compose build frontend`. Vite bakes it in at build time.
- **After frontend changes:** run `docker compose build frontend && docker compose up -d frontend`.
- **Development:** `npm run dev` on :5173 still works as before, with the Vite proxy and hot reload.
  Ports 8001 and 8002 stay published for Postman and tests.

The `frontend` service itself is in `docker-compose.frontend.yml`; paste it into
`backend/docker-compose.yml`.

## How it talks to the backend

The browser only talks to `localhost:5173`. The Vite dev server forwards requests (see `vite.config.ts`):

| Browser path | Goes to |
|---|---|
| `/auth/*`, `/users/*` | auth-service `:8001` (the path is kept, because the refresh cookie has `Path=/auth`) |
| `/api/*` | core-service `:8002`, with `/api` removed |

So there's no CORS setup, and the httpOnly refresh cookie just works. Override the targets with
`AUTH_URL` / `CORE_URL` in `.env` or the shell (see `.env.example`). `npm run preview` uses the same
proxy.

No app page lives under `/auth`, `/users` or `/api`, so reloading a page never hits the proxy. That's why
the Users page is at `/admin/users`.

**Tracing:** set `VITE_JAEGER_URL` (for example `http://localhost:16686`) in `.env`, or as a Docker build
arg. Each processing step that has a `trace_id` then shows "Open trace".

**Sign-in** (`src/api/session.ts`, `src/api/client.ts`):

- The access token is kept **in memory only**, never in localStorage.
- On load, the app calls `POST /auth/refresh` (cookie), then `GET /api/me` for the role.
- Any 401 triggers **one shared refresh**, then the request is retried once.
- If the refresh is **refused** (401 or another 4xx), you're signed out and sent to `/login?redirect=…`.
- If the backend **can't be reached** (network error or 5xx, for example a restart mid-demo), you stay
  signed in:
  - the failed request shows "Can't reach the server" and is retried;
  - the refresh is retried after 5 s, then 10 s, 20 s, and up to every 60 s;
  - on a page reload, the app retries 3 times, then shows a retry button instead of the login page.
- The token is refreshed about 60 s before it expires.
- Logout calls `POST /auth/logout` and clears the token.

**Errors:** every failure becomes an `ApiError` whose message is safe to show:

- App errors (400/404/409/422 with `{detail, code}`) show `detail` as the backend wrote it.
- FastAPI 422 lists appear next to the matching form fields.
- 403 shows "You don't have permission".
- 429 uses `Retry-After`.
- 5xx and network errors show a plain message with a retry button.
- Only network errors and 5xx are retried automatically.

## Screens

| Path | Who | What |
|---|---|---|
| `/login`, `/forgot-password`, `/reset-password` | everyone | Sign in, then a 6-digit code reset (the same message whether or not the email exists) |
| `/` | all | Counts (needs review, high severity, approved for admins, failed emails) and the latest submissions |
| `/review` | all | Queue with every filter in the URL, sorting, paging, flag badges, and bulk approve/reject with a result per row |
| `/timesheets/:id` | all | Editable days, pay breakdown with Recalculate, flags, match employee, approve/reject, banners, hours comparison, source and history |
| `/submissions`, `/submissions/:id` | all | Inbox with live polling; detail with documents (including how much of a large file was read), timesheets (refreshed once more when processing ends), a merged timeline (expand a step for input/output/errors, "Open trace" when tracing is set up), reprocess (with "Replace anyway" when approved timesheets would be replaced) and its runs |
| `/upload` | all | Drag and drop up to 10 files of 15 MB each, then follow the new submission live |
| `/export` | admin | Week picker locked to the company's week start; preview; `problems[]` block the export; create; history; CSV download |
| `/companies`, `/companies/:id` | read: all, edit: admin | Rates, rules, week start, active flag; allowed senders (whitelist) |
| `/employees` | read: all, edit: admin | Filter, add, edit |
| `/holidays` | read: all, edit: admin | Global or per company, by year |
| `/admin/users` | admin | Create, change role, deactivate/reactivate, set a password |
| `/account` | all | Profile, change password |

Reviewers never see Export or Users, and admin routes redirect them (`beforeLoad`). The backend checks
everything again anyway.

**Domain rules built into the UI:**

- The holiday checkbox edits `sheet_holiday` and is sent as `is_holiday`. The final `is_holiday`, which
  includes calendar holidays, is shown as a read-only badge.
- Hours go from 0 to 24 in steps of 0.25, all days must fall in the timesheet's week, and no day may
  repeat. These are checked before saving, and the backend's 422 is still shown.
- `exported` and `superseded` timesheets are read-only. A superseded timesheet links to its replacement.
- A missing rate shows "rate missing" and offers Recalculate.
- Lists of params are sent as repeated keys (`status=a&status=b`), which is what FastAPI expects.

## Folder layout

```
src/
  api/          client.ts (axios + refresh + errors), session.ts, core.ts, auth.ts, models.ts, queryKeys.ts, types/
  auth/         useSession, requireAdmin
  components/   AppShell, badges, states, pagination, fields, ui/ (button, dialog, table, …)
  features/     review/, timesheet/, submissions/, companies/, employees/
  lib/          format.ts, lookups.ts (company / employee names), severity.ts, forms.ts
  routes/       file routes: _auth/* (public), _app/* (signed in)
  app/          router, query client, providers, routeTree.gen.ts (generated by the router plugin)
tests/          Vitest
```

## Notes and known gaps

- **Names in the queue:** `TimesheetRead` only has `employee_id` and `company_id`. The app looks names up
  (all companies once, and employees per company, cached for 5 minutes, up to 100 per company). If you add
  `employee_name` and `company_name` to `TimesheetRead` in the backend, the UI uses them automatically
  (`src/lib/lookups.ts`).
- **Default sort:** the queue defaults to `sort=severity&order=desc`, meaning worst first. If your backend
  orders severity the other way, change `REVIEW_DEFAULTS` in `src/features/review/search.ts`.
- **`read_limit` shape:** the Documents card turns `DocumentRead.read_limit` into lines like "Read pages
  1–50 of 100" or "2 sheets not read". It accepts a plain message or an object with page, sheet or row
  counts (`src/features/submissions/readLimit.ts`). If your field names differ, add them to the key lists
  there.
- **Production:** serve `dist/` behind a reverse proxy with the same three path rules as the dev proxy, and
  set `REFRESH_COOKIE_SECURE=true` over https.
