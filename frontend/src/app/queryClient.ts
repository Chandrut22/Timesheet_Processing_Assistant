import { MutationCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, errorMessage } from "@/api/errors";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: {
      /** Set when the screen shows the error itself (e.g. inline in a form). */
      silentError?: boolean;
    };
  }
}

/**
 * Retry only what might succeed on its own: network failures and 5xx. Never 4xx, and
 * never 429: retrying a rate-limited request only uses up the next window too (the
 * message already tells the person how long to wait).
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (!(error instanceof ApiError)) return false;
  if (error.status === 429 || error.code === "rate_limit_unavailable") return false;
  return error.status === 0 || error.status >= 500;
}

export const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      if (mutation.meta?.silentError) return;
      toast.error(errorMessage(error));
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetry,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
