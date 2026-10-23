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
  Ports 8001 and 8002 are published by `backend/docker-compose.override.yml`, which Docker Compose loads
  automatically on a dev machine; a deployment runs `docker compose -f docker-compose.yml up -d` and
  publishes only the frontend.
- **nginx** (`nginx.conf`) sends a Content-Security-Policy and the other security headers on every
  response, replaces `X-Forwarded-For` with the real client address (the services rate-limit by it), and
  adds a per-IP rate limit in front of the services' own (`limit_req`). HSTS is there as a comment: turn it
  on once the site is served over HTTPS.

The `frontend` service itself is in `docker-compose.frontend.yml`; paste it into
`backend/docker-compose.yml`.

## How it talks to the backend

The browser only talks to `localhost:5173`. The Vite dev server forwards requests (see `vite.config.ts`):

| Browser path              | Goes to                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `/auth/*`, `/users/*` | auth-service `:8001` (the path is kept, because the refresh cookie has `Path=/auth`) |
| `/api/*`                | core-service `:8002`, with `/api` removed                                            |

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
- 429 uses `Retry-After`: "Too many requests. Try again in 12 seconds." for the per-endpoint rate limit
  (`code: "rate_limited"`), "Too many attempts…" for a sign-in or reset-code lockout.
- A 503 with `code: "rate_limit_unavailable"` (the rate limiter can't reach Redis and is set to fail
  closed) says the service is busy.
- 5xx and network errors show a plain message with a retry button.
- Only network errors and 5xx are retried automatically; never a 4xx, and never a 429 (a retry would
  only use up the next window).

**One HTTP client.** Every request goes through the axios instance in `src/api/client.ts`; screens call
the functions in `src/api/*.ts`. ESLint refuses `fetch()`, `XMLHttpRequest`, other HTTP libraries (ky,
ofetch, node-fetch, superagent, …) anywhere in `src/`, and axios itself outside `src/api/`.

## Keeping types in sync

The API types are **written by hand**, next to zod schemas that describe the same responses:

| File                                      | What                                                                                                                 |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `src/api/schemas/{common,auth,core}.ts` | zod schemas of what each service **sends**                                                                     |
| `src/api/types/{common,auth,core}.ts`   | the TypeScript types: responses `z.infer` from the schemas (so the two can't disagree), request bodies written out |
| `src/api/models.ts`                     | re-exports all of them; screens import from here                                                                     |

In `npm run dev` and in tests, every JSON response is checked against its schema (`checkResponse` in
`schemas/common.ts`). If the backend sends something the types don't describe, the call fails with an
error that names the endpoint and the field, in the console and on screen, instead of an `undefined`
deep inside a component. Production builds skip the check and return the response unchanged.

When you change a backend response model (a Pydantic `*Read` class, or `ImportReport`):

1. Change the matching schema in `src/api/schemas/` (field name, type, `.nullable()` for `X | None`,
   `.nullish()` when the field may be absent). Hours and money are sent as JSON numbers.
2. If it is a request body (`*Create`, `*Update`, `EntryInput`), change the type in `src/api/types/`.
3. Refresh `tests/fixtures/api-responses.json` with a real response for that endpoint (from `/docs` with
   `DOCS_ENABLED=true`, or the browser's network tab), then `npm test`: `tests/schemas.test.ts` checks
   every fixture against its schema.
4. `npm run typecheck` shows every screen the change affects.

## Bulk import

Admins get an **Import** button on Users, Employees, Companies and Holidays
(`src/features/import/ImportDialog.tsx`). Download the template, fill it in (CSV or the first sheet of an
XLSX), then **Check file**: a dry run that writes nothing and lists each row as created / updated /
skipped / failed, with the column of every problem. **Import** then sends the same file for real. Two
choices: whether one bad row stops the whole file (default) or only that row, and what to do with a
record that already exists (report it, skip it, or update it; users can't be updated from a file). New
users get the welcome email with their password; a blank password gets a random one.

## Screens

| Path                                                  | Who                    | What                                                                                                                                                                                                                                                                                                                                           |
| ----------------------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/login`, `/forgot-password`, `/reset-password` | everyone               | Sign in, then a 6-digit code reset (the same message whether or not the email exists)                                                                                                                                                                                                                                                          |
| `/`                                                 | all                    | Counts (needs review, high severity, approved for admins, failed emails) and the latest submissions                                                                                                                                                                                                                                            |
| `/review`                                           | all                    | Queue with every filter in the URL, sorting, paging, flag badges, and bulk approve/reject with a result per row                                                                                                                                                                                                                                |
| `/timesheets/:id`                                   | all                    | Editable days, pay breakdown with Recalculate, flags, match employee, approve/reject, banners, hours comparison, source and history                                                                                                                                                                                                            |
| `/submissions`, `/submissions/:id`                | all                    | Inbox with live polling; detail with documents (including how much of a large file was read), timesheets (refreshed once more when processing ends), a merged timeline (expand a step for input/output/errors, "Open trace" when tracing is set up), reprocess (with "Replace anyway" when approved timesheets would be replaced) and its runs |
| `/upload`                                           | all                    | Drag and drop up to 10 files of 15 MB each, then follow the new submission live                                                                                                                                                                                                                                                                |
| `/export`                                           | all                    | Week picker locked to the company's week start; preview; `problems[]` block the export; create; history; download as CSV or Excel (.xlsx)                                                                                                                                                                                                    |
| `/companies`, `/companies/:id`                    | read: all, edit: admin | Rates, rules, week start, active flag; allowed senders (whitelist); import from a file                                                                                                                                                                                                                                                         |
| `/employees`                                        | read: all, edit: admin | Filter, add, edit, import from a file                                                                                                                                                                                                                                                                                                          |
| `/holidays`                                         | read: all, edit: admin | Global or per company, by year; import from a file                                                                                                                                                                                                                                                                                             |
| `/admin/users`                                      | admin                  | Create, change role, deactivate/reactivate, set a password, import from a file                                                                                                                                                                                                                                                                 |
| `/account`                                          | all                    | Profile, change password                                                                                                                                                                                                                                                                                                                       |

**Roles.** Reviewers upload, review, reprocess and export payroll (CSV or Excel). Only admins manage
master data (companies, employees, holidays, allowed senders, bulk import) and users: reviewers see those
lists read-only, never see Users, and `/admin/users` redirects them (`beforeLoad: requireAdmin`). The
sidebar's role rules are in `src/components/nav.ts`. The backend checks everything again anyway.

**Domain rules built into the UI:**

- The holiday checkbox edits `sheet_holiday` and is sent as `is_holiday`. The final `is_holiday`, which
  includes calendar holidays, is shown as a read-only badge.
- Hours go from 0 to 24 in steps of 0.25, all days must fall in the timesheet's week, and no day may
  repeat. These are checked before saving, and the backend's 422 is still shown.
- `exported` timesheets are read-only. A reprocess updates timesheets in place; the **Versions** panel
  lists earlier versions (data changes only), shows their days and lets a reviewer restore one, which
  becomes a new version in review. Approve / reject are in the History panel.
- A missing rate shows "rate missing" and offers Recalculate.
- Lists of params are sent as repeated keys (`status=a&status=b`), which is what FastAPI expects.

## Folder layout

```
src/
  api/          client.ts (axios + refresh + errors), session.ts, core.ts, auth.ts, imports.ts, models.ts,
                queryKeys.ts, schemas/ (zod), types/
  auth/         useSession, requireAdmin
  components/   AppShell, badges, states, pagination, fields, ui/ (button, dialog, table, …)
  features/     review/, timesheet/, submissions/, companies/, employees/, import/, export/
  lib/          format.ts, lookups.ts (company / employee names), severity.ts, forms.ts
  routes/       file routes: _auth/* (public), _app/* (signed in)
  app/          router, query client, providers, routeTree.gen.ts (generated by the router plugin)
tests/          Vitest (*.test.ts in Node; *.test.tsx component tests in jsdom), fixtures/
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
