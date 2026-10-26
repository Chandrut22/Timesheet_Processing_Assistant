import { z } from "zod";
import { env } from "@/config/env";

/** On in `npm run dev` and in tests; off in production builds (no cost, no new failure). */
const CHECK_RESPONSES = env.isDev || env.isTest;

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
 * `schema`, so a backend change that the feature types don't know about fails
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

/** `http.get(url)` checked against `schema` (dev / test) and typed by it. */
export const checked = <T>(schema: z.ZodType<T>, p: Promise<Response>): Promise<T> =>
  p.then(responseOf(schema));
