import {
  useQuery,
  useQueryClient,
  type UseQueryResult,
  type DefaultError,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { DashboardSnapshot } from "../types/dashboard";
import { SseError } from "@/lib/sse";
import { streamDashboard } from "../services/dashboardStream";
import { dashboardService } from "../services/dashboardService";
import { dashboardKeys } from "../queries/dashboardQueries";

export type StreamState = "connecting" | "live" | "reconnecting";

const sleep = (ms: number, signal: AbortSignal): Promise<void> =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(timer), resolve()), { once: true });
  });

/** The dashboard numbers, kept live by the stream. While the stream is down the
 *  query polls every 15 s, so the page never freezes. */
export function useDashboard(): UseQueryResult<DashboardSnapshot, DefaultError> & {
  stream: StreamState;
} {
  const qc = useQueryClient();
  const [stream, setStream] = useState<StreamState>("connecting");

  const query = useQuery({
    queryKey: dashboardKeys.snapshot(),
    queryFn: dashboardService.getDashboard,
    refetchInterval: stream === "live" ? false : 15_000,
  });

  useEffect(() => {
    const ctrl = new AbortController();
    void (async () => {
      let delay = 1_000;
      while (!ctrl.signal.aborted) {
        try {
          await streamDashboard((m) => {
            if (m.event === "snapshot") {
              qc.setQueryData(dashboardKeys.snapshot(), JSON.parse(m.data) as DashboardSnapshot);
              setStream("live");
              delay = 1_000;
            }
            // "reauth" or the stream ending: the loop reconnects with a fresh token
          }, ctrl.signal);
        } catch (err) {
          if (ctrl.signal.aborted) return;
          if (err instanceof SseError && err.status === 401) return; // signed out: the layout redirects
        }
        if (ctrl.signal.aborted) return;
        setStream("reconnecting");
        await sleep(delay, ctrl.signal);
        delay = Math.min(delay * 2, 30_000);
      }
    })();
    return () => ctrl.abort();
  }, [qc]);

  return { ...query, stream };
}
