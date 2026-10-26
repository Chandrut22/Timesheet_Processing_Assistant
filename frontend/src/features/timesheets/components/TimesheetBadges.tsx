import type { FlagRead } from "../types/timesheet";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { flagLabel } from "../utils/flags";
import { humanize } from "@/utils/format";
import { sortFlags } from "../utils/severity";
import { cn } from "@/lib/utils";

const TIMESHEET_TONE: Record<string, BadgeVariant> = {
  needs_review: "warning",
  approved: "success",
  rejected: "danger",
  exported: "info",
};

export function TimesheetStatusBadge({ status }: { status: string }) {
  return <Badge variant={TIMESHEET_TONE[status] ?? "secondary"}>{humanize(status)}</Badge>;
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
          {flagLabel(f.code)}
        </Badge>
      ))}
      {sorted.length > max ? <Badge variant="muted">+{sorted.length - max}</Badge> : null}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={severityVariant(severity)}>{humanize(severity)}</Badge>;
}
