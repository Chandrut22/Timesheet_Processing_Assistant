import { isAxiosError, isCancel } from "axios";

/** Every failed API call becomes one of these. `message` is safe to show to people. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly fieldErrors: Record<string, string>;
  readonly retryAfter: number | null;

  constructor(opts: {
    status: number;
    message: string;
    code?: string | null;
    fieldErrors?: Record<string, string>;
    retryAfter?: number | null;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code ?? null;
    this.fieldErrors = opts.fieldErrors ?? {};
    this.retryAfter = opts.retryAfter ?? null;
  }
}

export const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again.";
export const SERVER_MESSAGE = "Something went wrong on our side. Please try again.";
export const FORBIDDEN_MESSAGE = "You don't have permission to do that.";
export const BUSY_MESSAGE = "The service is busy. Please try again in a few seconds.";

type ValidationItem = { loc?: unknown; msg?: unknown };

const LOC_PREFIXES = new Set(["body", "query", "path", "header", "cookie"]);

/** ['body', 'entries', 0, 'hours'] -> 'entries.0.hours' (matches react-hook-form paths). */
export function locToField(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  return loc
    .filter((part, i) => !(i === 0 && typeof part === "string" && LOC_PREFIXES.has(part)))
    .map(String)
    .join(".");
}

function humanizeField(field: string): string {
  const last =
    field
      .split(".")
      .filter((p) => !/^\d+$/.test(p))
      .pop() ?? field;
  const words = last.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function parseRetryAfter(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const n = Number(value);
  if (Number.isFinite(n)) return Math.max(0, Math.round(n));
  const date = Date.parse(String(value));
  if (Number.isNaN(date)) return null;
  return Math.max(0, Math.round((date - Date.now()) / 1000));
}

/** Pure mapping from (status, body, retry-after) to an ApiError. Unit-tested. */
export function buildApiError(status: number, data: unknown, retryAfterHeader?: unknown): ApiError {
  const body = (data && typeof data === "object" ? data : {}) as {
    detail?: unknown;
    code?: unknown;
    message?: unknown;
  };
  const code = typeof body.code === "string" ? body.code : null;
  const detail = body.detail;

  // The rate limiter could not count (Redis down, RATE_LIMIT_FAIL_OPEN=false).
  if (status === 503 && code === "rate_limit_unavailable") {
    return new ApiError({
      status,
      message: BUSY_MESSAGE,
      code,
      retryAfter: parseRetryAfter(retryAfterHeader),
    });
  }
  // A part of the system is not running (e.g. the email listener): its message says which.
  if (status === 503 && code === "email_listener_down" && typeof detail === "string") {
    return new ApiError({ status, message: detail, code });
  }
  if (status >= 500) return new ApiError({ status, message: SERVER_MESSAGE, code });

  if (status === 429) {
    // "rate_limited": the per-endpoint limit (any screen). Otherwise a sign-in or
    // reset-code lockout from auth-service, which is about attempts.
    const what = code === "rate_limited" ? "Too many requests" : "Too many attempts";
    const retryAfter = parseRetryAfter(retryAfterHeader);
    if (code === "check_cooldown" && typeof detail === "string") {
      return new ApiError({ status, message: detail, code, retryAfter });
    }
    const message =
      retryAfter !== null
        ? `${what}. Try again in ${retryAfter} ${retryAfter === 1 ? "second" : "seconds"}.`
        : typeof detail === "string"
          ? detail
          : `${what}. Please wait a moment and try again.`;
    return new ApiError({ status, message, code, retryAfter });
  }

  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const item of detail as ValidationItem[]) {
      const field = locToField(item.loc);
      const msg = typeof item.msg === "string" ? item.msg : "Invalid value";
      if (field && !(field in fieldErrors)) fieldErrors[field] = msg;
    }
    const first = Object.entries(fieldErrors)[0];
    const message = first ? `${humanizeField(first[0])}: ${first[1]}` : "Please check the form.";
    return new ApiError({ status, message, code: code ?? "validation_error", fieldErrors });
  }

  if (status === 403) return new ApiError({ status, message: FORBIDDEN_MESSAGE, code });

  if (typeof detail === "string" && detail.trim()) {
    return new ApiError({ status, message: detail, code });
  }
  if (typeof body.message === "string" && body.message.trim()) {
    return new ApiError({ status, message: body.message, code });
  }
  if (status === 404) return new ApiError({ status, message: "Not found.", code });
  if (status === 401) return new ApiError({ status, message: "Please sign in again.", code });
  return new ApiError({ status, message: "The request could not be completed.", code });
}

async function readBody(data: unknown): Promise<unknown> {
  // Blob responses (CSV download) carry their JSON error body as a Blob.
  if (typeof Blob !== "undefined" && data instanceof Blob) {
    try {
      return JSON.parse(await data.text());
    } catch {
      return null;
    }
  }
  return data;
}

export const CANCELLED_MESSAGE = "The request was cancelled.";

export async function toApiError(err: unknown): Promise<ApiError> {
  if (err instanceof ApiError) return err;
  // A search replaced by a newer one (TanStack Query aborted it): not a network failure.
  if (isCancel(err))
    return new ApiError({ status: 0, message: CANCELLED_MESSAGE, code: "cancelled" });
  if (isAxiosError(err)) {
    if (!err.response)
      return new ApiError({ status: 0, message: NETWORK_MESSAGE, code: "network" });
    const data = await readBody(err.response.data);
    const headers = err.response.headers as Record<string, unknown> | undefined;
    return buildApiError(err.response.status, data, headers?.["retry-after"]);
  }
  return new ApiError({ status: -1, message: "Something went wrong. Please try again." });
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

export function isApiError(err: unknown, status?: number): err is ApiError {
  return err instanceof ApiError && (status === undefined || err.status === status);
}
