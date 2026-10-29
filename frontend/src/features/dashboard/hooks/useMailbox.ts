import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
  type DefaultError,
} from "@tanstack/react-query";
import { mailboxKeys } from "../queries/dashboardQueries";
import { mailboxService } from "../services/mailboxService";
import type { MailboxCheck, MailboxStatus } from "../types/mailbox";

const POLL_MS = 2_000;
const GIVE_UP_MS = 60_000;
const FINAL = new Set<MailboxCheck["state"]>(["done", "failed"]);

const sleep = (ms: number): Promise<void> =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

/** The email listener's status: running? when did it last check? Refreshed every 30 s. */
export function useMailboxStatus(): UseQueryResult<MailboxStatus, DefaultError> {
  return useQuery({
    queryKey: mailboxKeys.status(),
    queryFn: mailboxService.getStatus,
    refetchInterval: 30_000,
  });
}

/**
 * Follow one "Check mail now" request: ask every `pollMs` until it is done or failed.
 * null when it is still not finished after `giveUpMs`.
 */
export async function followCheck(
  requestId: string,
  get: (id: string) => Promise<MailboxCheck> = mailboxService.getCheck,
  wait: (ms: number) => Promise<void> = sleep,
  pollMs = POLL_MS,
  giveUpMs = GIVE_UP_MS,
): Promise<MailboxCheck | null> {
  for (let waited = 0; waited < giveUpMs; waited += pollMs) {
    await wait(pollMs);
    const check = await get(requestId);
    if (FINAL.has(check.state)) return check;
  }
  return null;
}

/**
 * "Check mail now": asks the listener to read the mailbox and follows the request until
 * it ends (one mutation, so there is no state to keep in sync). `onFinished` gets the
 * result, or null when it took longer than a minute; `onError` a refused request
 * (cooldown, listener not running).
 */
export function useCheckMailNow({
  onFinished,
  onError,
}: {
  onFinished: (check: MailboxCheck | null) => void;
  onError: (error: Error) => void;
}): { checkNow: () => void; busy: boolean } {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async () => {
      const started = await mailboxService.checkNow();
      return FINAL.has(started.state) ? started : followCheck(started.request_id);
    },
    meta: { silentError: true }, // onError shows the server's own message
    onSuccess: onFinished,
    onError,
    onSettled: () => void qc.invalidateQueries({ queryKey: mailboxKeys.status() }),
  });
  return { checkNow: () => m.mutate(), busy: m.isPending };
}
