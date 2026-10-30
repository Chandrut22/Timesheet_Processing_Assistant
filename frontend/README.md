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
- **After frontend changes:** run `docker compose build frontend && docker compose up -d frontend`.
- **Development:** `npm run dev` on :5173 still works as before, with the Vite proxy and hot reload.
  Ports 8001 and 8002 are published by `backend/docker-compose.override.yml`, which Docker Compose loads
  automatically on a dev machine; a deployment runs `docker compose -f docker-compose.yml up -d` and
  publishes only the frontend.
- **nginx** (`nginx.conf`) sends a Content-Security-Policy and the other security headers on every
  response and sets `X-Real-IP` to the real client address (the services' one rate limit, 100 requests a
  minute per IP for every endpoint, counts by it). HSTS is there as a comment: turn it on once the site is
  served over HTTPS.

The `frontend` service itself is in `docker-compose.frontend.yml`; paste it into
`backend/docker-compose.yml`.

## How it talks to the backend

The browser only talks to `localhost:5173`. The Vite dev server forwards requests (see `vite.config.ts`):

| Browser path          | Goes to                                                                              |
| --------------------- | ------------------------------------------------------------------------------------ |
| `/auth/*`, `/users/*` | auth-service `:8001` (the path is kept, because the refresh cookie has `Path=/auth`) |
| `/api/*`              | core-service `:8002`, with `/api` removed                                            |

So there's no CORS setup, and the httpOnly refresh cookie just works. Override the targets with
`AUTH_URL` / `CORE_URL` in `.env` or the shell (see `.env.example`). `npm run preview` uses the same
proxy.

No app page lives under `/auth`, `/users` or `/api`, so reloading a page never hits the proxy. That's why
the Users page is at `/admin/users`.

**Sign-in** (`src/services/session.ts`, `src/lib/axios.ts`):

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
- 429 uses `Retry-After`: "Too many requests. Try again in 12 seconds." for the rate limit (100 requests
  a minute per IP, all endpoints of both services together; `code: "rate_limited"`), "Too many attempts…" for a sign-in or reset-code lockout.
- A 503 with `code: "rate_limit_unavailable"` (the rate limiter can't reach Redis and is set to fail
  closed) says the service is busy.
- 5xx and network errors show a plain message with a retry button.
- Only network errors and 5xx are retried automatically; never a 4xx, and never a 429 (a retry would
  only use up the next window).

**One HTTP client.** Every request goes through the axios instance in `src/lib/axios.ts`; screens call
the feature services (`src/features/*/services/*Service.ts`). ESLint refuses `fetch()`, `XMLHttpRequest`,
other HTTP libraries (ky, ofetch, node-fetch, superagent, …) anywhere in `src/`, and axios itself outside
`src/lib/axios.ts`, `src/services/session.ts` and `src/services/apiErrors.ts`.

## Keeping types in sync

The API types are **written by hand**, next to zod schemas that describe the same responses:

| File                             | What                                                                                                                   |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `src/features/<name>/types/*.ts` | each feature's zod schemas of what the service **sends**, and its TypeScript types (`z.infer`, so they can't disagree) |
| `src/services/schemas.ts`        | shared building blocks (`uuid`, `decimal`, `isoDate`, `pageOf`, …) and the shared principal / bulk schemas             |
| `src/types/api.ts`               | shared types (`Page`, `RoleName`, `SortOrder`, `Bulk*`, …)                                                             |
| `src/services/response.ts`       | `checkResponse` / `checked`: the dev-time check of every response                                                      |

In `npm run dev` and in tests, every JSON response is checked against its schema (`checkResponse` in
`src/services/response.ts`). If the backend sends something the types don't describe, the call fails with an
error that names the endpoint and the field, in the console and on screen, instead of an `undefined`
deep inside a component. Production builds skip the check and return the response unchanged.

When you change a backend response model (a Pydantic `*Read` class, or `ImportReport`):

1. Change the matching schema in `src/features/<name>/types/` (field name, type, `.nullable()` for `X | None`,
   `.nullish()` when the field may be absent). Hours and money are sent as JSON numbers.
2. If it is a request body (`*Create`, `*Update`, `EntryInput`), change the type in the same file.
3. Refresh `src/test/fixtures/api-responses.json` with a real response for that endpoint (from `/docs` with
   `DOCS_ENABLED=true`, or the browser's network tab), then `npm test`: `src/services/schemas.test.ts` checks
   every fixture against its schema.
4. `npm run typecheck` shows every screen the change affects.

## Bulk import

Admins get an **Import** button on Users, Employees, Companies and Holidays
(`src/features/import/components/ImportDialog.tsx`). Download the template, fill it in (CSV or the first sheet of an
XLSX), then **Check file**: a dry run that writes nothing and lists each row as created / updated /
skipped / failed, with the column of every problem. **Import** then sends the same file for real. Two
choices: whether one bad row stops the whole file (default) or only that row, and what to do with a
record that already exists (report it, skip it, or update it; users can't be updated from a file). New
users get the welcome email with their password; a blank password gets a random one.

## Screens

| Path                                            | Who                    | What                                                                                                                                                                                                                                                                                                      |
| ----------------------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/login`, `/forgot-password`, `/reset-password` | everyone               | Sign in, then a 6-digit code reset (the same message whether or not the email exists)                                                                                                                                                                                                                     |
| `/`                                             | all                    | Counts (needs review, high severity, approved for admins, failed emails) and the latest submissions                                                                                                                                                                                                       |
| `/review`                                       | all                    | Queue with every filter in the URL, sorting, paging, flag badges, and bulk approve/reject with a result per row                                                                                                                                                                                           |
| `/timesheets/:id`                               | all                    | Editable days, pay breakdown with Recalculate, flags, match employee, approve/reject, banners, hours comparison, source and history                                                                                                                                                                       |
| `/submissions`, `/submissions/:id`              | all                    | Inbox with live polling; detail with documents (including how much of a large file was read), timesheets (refreshed once more when processing ends), a merged timeline (expand a step for input/output/errors), reprocess (with "Replace anyway" when approved timesheets would be replaced) and its runs |
| `/upload`                                       | all                    | Drag and drop up to 10 files of 15 MB each, then follow the new submission live                                                                                                                                                                                                                           |
| `/export`                                       | all                    | Week picker locked to the company's week start; preview; `problems[]` block the export; create; history; download as CSV or Excel (.xlsx)                                                                                                                                                                 |
| `/companies`, `/companies/:id`                  | read: all, edit: admin | Rates, rules, week start, active flag; allowed senders (whitelist); import from a file                                                                                                                                                                                                                    |
| `/employees`                                    | read: all, edit: admin | Filter, add, edit, import from a file                                                                                                                                                                                                                                                                     |
| `/holidays`                                     | read: all, edit: admin | Global or per company, by year; import from a file                                                                                                                                                                                                                                                        |
| `/admin/users`                                  | admin                  | Create, change role, deactivate/reactivate, set a password, import from a file                                                                                                                                                                                                                            |
| `/account`                                      | all                    | Profile, change password                                                                                                                                                                                                                                                                                  |

**Roles.** Reviewers upload, review, reprocess and export payroll (CSV or Excel). Only admins manage
master data (companies, employees, holidays, allowed senders, bulk import) and users: reviewers see those
lists read-only, never see Users, and `/admin/users` redirects them (`beforeLoad: requireAdmin`). The
sidebar's role rules are in `src/layouts/nav.ts`. The backend checks everything again anyway.

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

Code is grouped by **feature**. Each feature folder holds everything for one part of the app and exposes
a public API in its `index.ts`; the rest of the app imports only from `@/features/<name>`, never from a
file inside it (ESLint enforces this; tests may reach in to mock one module). Inside a feature, files
import each other with relative paths. Two exceptions, both enforced by ESLint: **pages are not in
`index.ts`** (only their route file imports them, see [Code splitting](#code-splitting)), and
**components never call services or `useQuery` / `useMutation`**: they use the feature's hooks
(Component → Hook → Service → API client).

```
src/
  app/          router.ts, queryClient.ts, providers.tsx, devtools.tsx, routeTree.gen.ts (generated)
  assets/       images and fonts imported by code
  components/
    ui/         shadcn primitives (button, dialog, table, …)
    common/     shared building blocks: States, Pagination, SortHeader, ConfirmDialog, BulkStatusBar, …
    forms/      Field, FormError, DebouncedInput
  config/       env.ts (typed import.meta.env), constants.ts
  features/
    <name>/     account, audit, auth, companies, dashboard, employees, export, holidays, import,
                review, submissions, timesheets, upload, users
      components/   the feature's screens (<Name>Page.tsx) and their parts
      hooks/        React hooks: every query and mutation (useCompaniesList, useUpdateCompany, …)
      queries/      TanStack Query keys (<name>Keys)
      services/     typed API calls through the shared axios client (<name>Service)
      types/        zod schemas and TypeScript types for the feature's API
      utils/        pure helpers, and the page's URL validator (<name>Search.ts)
      index.ts      the public API (hooks, types, small helpers; never a page)
  hooks/        shared hooks (useDebounce, useRowSelection)
  layouts/      AppShell, nav.ts (sidebar + role rules), AuthLayout, AuthBackground
  lib/          axios.ts (the HTTP client: token, refresh, errors), sse.ts, forms.ts, utils.ts (cn)
  routes/       TanStack file routes; each file only wires a path to a page and its URL validator
  services/     session.ts (sign-in, refresh, logout), apiErrors.ts, response.ts, schemas.ts
  styles/       global CSS
  test/         render.tsx (renderWithClient), fixtures/api-responses.json
  types/        shared API types (api.ts), vite-env.d.ts
  utils/        format.ts, rowSelection.ts, errors.ts (ApiError, errorMessage), chunkError.ts
```

Tests sit next to the file they cover (`Foo.test.ts` beside `Foo.ts`). `*.test.ts` run in Node;
`*.test.tsx` component tests start with `// @vitest-environment jsdom`.

**Adding a screen:** create `src/features/<name>/components/<Name>Page.tsx` (read the URL with
`getRouteApi("<route id>")`), its data hooks in `hooks/`, and, if it has URL parameters, a validator in
`utils/<name>Search.ts`. Then add a thin route file in `src/routes/` that imports the page and the
validator **directly** (`@/features/<name>/components/<Name>Page`), not from the feature's `index.ts`.

## Code splitting

Every page is loaded only when it is first opened. This is done by TanStack Router's
**`autoCodeSplitting: true`** (in `vite.config.ts`): at build time the router plugin moves each route's
`component` into its own chunk and loads it on demand. That is TanStack's recommended way, so there is
**no `React.lazy()`** in the app: wrapping pages in `React.lazy` as well would split them twice. (A
checker that only searches for `React.lazy` will not see this; `npm run build` lists one chunk per page.)

What keeps it working:

- Route files import the page **directly**. If a page were exported from its feature's `index.ts`, every
  other import of that feature (a hook, a type) would bring the page into the main chunk.
  `src/app/codeSplitting.test.ts` and an ESLint rule on `src/routes/**` check this.
- A page's URL validator lives in `utils/<name>Search.ts`, not in the page: the validator is needed at
  once (to read the URL), the page only when it is shown.
- While a page's chunk loads, the router shows `PagePending` (after 1 s, for at least 300 ms), and
  hovering a link already starts loading it (`defaultPreload: "intent"`).
- After a deploy, a tab opened earlier may ask for an old chunk that no longer exists. The route error
  then says **"A new version of the app is available"** with a Reload button (`RouteError`,
  `utils/chunkError.ts`), instead of a generic error.

## Notes and known gaps

- **Names in the queue:** `TimesheetRead` only has `employee_id` and `company_id`. The app looks names up
  (all companies once, and employees per company, cached for 5 minutes, up to 100 per company). If you add
  `employee_name` and `company_name` to `TimesheetRead` in the backend, the UI uses them automatically
  (`src/features/timesheets/utils/names.ts`).
- **Default sort:** the queue defaults to `sort=severity&order=desc`, meaning worst first. If your backend
  orders severity the other way, change `REVIEW_DEFAULTS` in `src/features/review/utils/search.ts`.
- **`read_limit` shape:** the Documents card turns `DocumentRead.read_limit` into lines like "Read pages
  1–50 of 100" or "2 sheets not read". It accepts a plain message or an object with page, sheet or row
  counts (`src/features/submissions/utils/readLimit.ts`). If your field names differ, add them to the key lists
  there.
- **Production:** serve `dist/` behind a reverse proxy with the same three path rules as the dev proxy, and
  set `REFRESH_COOKIE_SECURE=true` over https.
