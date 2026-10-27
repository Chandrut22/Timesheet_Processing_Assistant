// "Check mail now" on the dashboard: the email listener's status line and a button that
// makes it read the mailbox at once. Hidden when reading email is turned off.
import { MailCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/services/apiErrors";
import { formatRelative } from "@/utils/format";
import { cn } from "@/lib/utils";
import { useCountdown } from "../hooks/useCountdown";
import { useCheckMailNow, useMailboxStatus } from "../hooks/useMailbox";
import type { MailboxCheck } from "../types/mailbox";
import { describeCheck } from "../utils/describeCheck";

function showResult(check: MailboxCheck | null) {
  if (!check) toast.warning("The mailbox check is taking long. The results will appear below.");
  else if (check.state === "failed") toast.error(check.error ?? "The mailbox check failed.");
  else toast.success(describeCheck(check));
}

export function MailCheckButton() {
  const status = useMailboxStatus();
  const s = status.data;
  const cooldown = useCountdown(s?.cooldown_seconds ?? 0, status.dataUpdatedAt);
  const mail = useCheckMailNow({
    onFinished: showResult,
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (!s || s.enabled === false) return null;

  const label = mail.busy
    ? "Checking…"
    : cooldown > 0
      ? `Check mail now (${cooldown}s)`
      : "Check mail now";
  const line = !s.running
    ? `Email listener not running${s.last_error ? `: ${s.last_error}` : ""}`
    : !s.connected
      ? "Email listener reconnecting"
      : s.last_check_at
        ? `Email checked ${formatRelative(s.last_check_at)}`
        : "Email listener running";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        role="status"
        className="inline-flex max-w-80 items-center gap-1.5 truncate text-xs text-muted-foreground"
        title={s.mailbox ?? undefined}
      >
        <span
          className={cn(
            "size-2 shrink-0 rounded-full",
            !s.running ? "bg-destructive" : s.connected ? "bg-emerald-500" : "bg-amber-500",
          )}
        />
        <MailCheck className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{line}</span>
      </span>
      <Button
        size="sm"
        variant="outline"
        onClick={mail.checkNow}
        disabled={mail.busy || cooldown > 0 || !s.running}
        title={
          !s.running
            ? "The email listener is not running"
            : cooldown > 0
              ? `Wait ${cooldown} s`
              : `Read ${s.mailbox ?? "the mailbox"} now`
        }
      >
        <RefreshCw className={cn(mail.busy && "motion-safe:animate-spin")} aria-hidden />
        {label}
      </Button>
    </div>
  );
}
