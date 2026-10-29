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

export const pageOf = <T extends z.ZodType>(
  item: T,
): z.ZodObject<{ items: z.ZodArray<T>; total: typeof int; page: typeof int; size: typeof int }> =>
  z.object({ items: z.array(item), total: int, page: int, size: int });

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

export const SortOrderSchema = z.enum(["asc", "desc"]);

export const PrincipalReadSchema = z.object({
  id: uuid,
  role: RoleNameSchema,
  name: z.string(),
  email: z.string(),
});

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: int,
});
