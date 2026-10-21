import { Mail, Upload } from "lucide-react";
import type { FlagRead } from "@/api/models";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import { IN_PROGRESS_STATES } from "@/lib/submissionStates";
import { sortFlags } from "@/lib/severity";
import { cn } from "@/lib/utils";

const TIMESHEET_TONE: Record<string, BadgeVariant> = {
  needs_review: "warning",
  approved: "success",
  rejected: "danger",
  exported: "info",
  superseded: "muted",
};

export function TimesheetStatusBadge({ status }: { status: string }) {
  return <Badge variant={TIMESHEET_TONE[status] ?? "secondary"}>{humanize(status)}</Badge>;
}

const STATE_TONE: Record<string, BadgeVariant> = {
  received: "secondary",
  reading: "info",
  matching: "info",
  rule_checks: "info",
  reprocessing: "info",
  awaiting_review: "warning",
  approved: "success",
  rejected: "danger",
  exported: "info",
  ignored: "muted",
  failed: "danger",
};

const STATE_LABEL: Record<string, string> = {
  rule_checks: "Checking rules",
  awaiting_review: "Awaiting review",
};

export function SubmissionStateBadge({ state }: { state: string }) {
  const busy = IN_PROGRESS_STATES.has(state);
  return (
    <Badge variant={STATE_TONE[state] ?? "secondary"}>
      {busy ? (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      ) : null}
      {STATE_LABEL[state] ?? humanize(state)}
    </Badge>
  );
}

const STATUS_TONE: Record<string, BadgeVariant> = {
  received: "secondary",
  processing: "info",
  processed: "success",
  failed: "danger",
  ignored: "muted",
};

export function SubmissionStatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_TONE[status] ?? "secondary"}>{humanize(status)}</Badge>;
}

export function SourceIcon({ source }: { source: string }) {
  return source === "upload" ? (
    <Upload className="size-4 text-muted-foreground" aria-label="Upload" />
  ) : (
    <Mail className="size-4 text-muted-foreground" aria-label="Email" />
  );
}

const DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-sky-500",
};

export function SeverityDot({ severity }: { severity: string | null }) {
  const label = severity ? `${humanize(severity)} severity` : "No flags";
  return (
    <span
      className={cn(
        "inline-block size-2.5 rounded-full",
        severity ? DOT[severity] : "bg-emerald-500",
      )}
      title={label}
      aria-label={label}
      role="img"
    />
  );
}

function severityVariant(s: string): BadgeVariant {
  return s === "high" || s === "medium" || s === "low" ? s : "secondary";
}

export function FlagBadges({ flags, max = 3 }: { flags: FlagRead[]; max?: number }) {
  if (flags.length === 0) return <span className="text-muted-foreground">—</span>;
  const sorted = sortFlags(flags);
  const shown = sorted.slice(0, max);
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((f, i) => (
        <Badge key={`${f.code}-${i}`} variant={severityVariant(f.severity)} title={f.message}>
          {humanize(f.code)}
        </Badge>
      ))}
      {sorted.length > max ? <Badge variant="muted">+{sorted.length - max}</Badge> : null}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={severityVariant(severity)}>{humanize(severity)}</Badge>;
}
