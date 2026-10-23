// Building blocks shared by the auth and core schemas, and the dev-time response check.
//
// These schemas are written by hand from the backend's Pydantic models (see the README,
// "Keeping types in sync"). They describe what the API SENDS; request bodies are plain
// TypeScript types in ../types.
import { z } from "zod";

export const uuid = z.uuid();
/** "2026-10-12" */
export const isoDate = z.iso.date();
/** "2026-10-12T09:30:00.123456+00:00" (the backend always sends an offset). */
export const isoDateTime = z.iso.datetime({ offset: true });
/** Hours and money: Decimal on the backend, sent as JSON numbers. */
export const decimal = z.number();
export const int = z.number().int();
/** Free-form JSON objects (step input / output, audit details, ...). */
export const jsonObject = z.record(z.string(), z.unknown());

export const RoleNameSchema = z.enum(["admin", "reviewer"]);

export const pageOf = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), total: int, page: int, size: int });

// --- bulk import report (same shape from auth-service and core-service) ------------

export const OnErrorSchema = z.enum(["abort", "skip"]);
export const OnDuplicateSchema = z.enum(["error", "skip", "update"]);
export const RowStatusSchema = z.enum(["created", "updated", "skipped", "failed"]);

export const CellErrorSchema = z.object({ column: z.string().nullable(), message: z.string() });

export const RowResultSchema = z.object({
  row: int,
  status: RowStatusSchema,
  errors: z.array(CellErrorSchema),
  warnings: z.array(z.string()),
});

export const ImportReportSchema = z.object({
  resource: z.string(),
  file_name: z.string(),
  dry_run: z.boolean(),
  committed: z.boolean(),
  on_error: OnErrorSchema,
  on_duplicate: OnDuplicateSchema,
  total_rows: int,
  created: int,
  updated: int,
  skipped: int,
  failed: int,
  warnings: z.array(z.string()),
  rows: z.array(RowResultSchema),
  rows_omitted: int,
});

// --- bulk activate / deactivate / delete (same item shape from both services) -------

export const BulkStatusItemSchema = z.object({
  id: uuid,
  ok: z.boolean(),
  /** False when it already had that status (or failed). */
  changed: z.boolean(),
  /** The status afterwards (null when not found, or after a delete). */
  is_active: z.boolean().nullable(),
  error: z.string().nullable(),
});

export const BulkStatusResultSchema = z.object({
  requested: int,
  succeeded: int,
  failed: int,
  results: z.array(BulkStatusItemSchema),
  /** Companies only: employees deactivated with them (auth-service leaves it out). */
  employees_deactivated: int.optional(),
});

export const BulkDeleteResultSchema = z.object({
  requested: int,
  deleted: int,
  failed: int,
  results: z.array(BulkStatusItemSchema),
});

// --- the dev-time check ---------------------------------------------------------------

/** On in `npm run dev` and in tests; off in production builds (no cost, no new failure). */
const CHECK_RESPONSES = import.meta.env.DEV || import.meta.env.MODE === "test";

/** Thrown in dev / test when the backend sends something the frontend types don't describe. */
export class ResponseShapeError extends Error {
  readonly issues: z.core.$ZodIssue[];

  constructor(what: string, error: z.ZodError) {
    super(
      `The API response for ${what} does not match the frontend types:\n${z.prettifyError(error)}`,
    );
    this.name = "ResponseShapeError";
    this.issues = error.issues;
  }
}

/**
 * Returns `value` unchanged, typed as T. In dev and tests it is first checked against
 * `schema`, so a backend change that the types in src/api/types don't know about fails
 * loudly where a developer sees it, instead of as `undefined` deep inside a screen.
 * The value is never replaced by the parsed copy, so dev and production behave alike.
 */
export function checkResponse<T>(schema: z.ZodType<T>, value: unknown, what: string): T {
  if (CHECK_RESPONSES) {
    const result = schema.safeParse(value);
    if (!result.success) {
      const error = new ResponseShapeError(what, result.error);
      console.error(error.message);
      throw error;
    }
  }
  return value as T;
}

type Response = { data: unknown; config?: { method?: string; url?: string } };

/** `http.get(url).then(responseOf(Schema))`: the body, checked (dev / test) and typed. */
export const responseOf =
  <T>(schema: z.ZodType<T>) =>
  (res: Response): T =>
    checkResponse(
      schema,
      res.data,
      `${res.config?.method?.toUpperCase() ?? ""} ${res.config?.url ?? ""}`.trim(),
    );
