// The error every failed API call becomes, and how screens show it. No network code
// here (services/apiErrors.ts turns axios errors into ApiError), so components may
// import it directly.

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

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

export function isApiError(err: unknown, status?: number): err is ApiError {
  return err instanceof ApiError && (status === undefined || err.status === status);
}
