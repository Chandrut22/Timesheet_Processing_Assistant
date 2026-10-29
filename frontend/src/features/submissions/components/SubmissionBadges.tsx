import { Mail, Upload } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { humanize } from "@/utils/format";
import { IN_PROGRESS_STATES } from "../utils/submissionStates";
import { writingChip } from "../utils/writing";
import type { JSX } from "react";

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

export function SubmissionStateBadge({ state }: { state: string }): JSX.Element {
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

export function SubmissionStatusBadge({ status }: { status: string }): JSX.Element {
  return <Badge variant={STATUS_TONE[status] ?? "secondary"}>{humanize(status)}</Badge>;
}

export function SourceIcon({ source }: { source: string }): JSX.Element {
  return source === "upload" ? (
    <Upload className="size-4 text-muted-foreground" aria-label="Upload" />
  ) : (
    <Mail className="size-4 text-muted-foreground" aria-label="Email" />
  );
}

/** On a photo / scan read by the vision model: printed, mixed, handwritten or unclear. */
export function WritingClassChip({
  doc,
}: {
  doc: Parameters<typeof writingChip>[0];
}): JSX.Element | null {
  const chip = writingChip(doc);
  if (!chip) return null;
  return (
    <Badge variant={chip.tone} title={chip.title}>
      {chip.label}
      {doc.unclear_marks > 0 ? (
        <span className="tabular">· {doc.unclear_marks} unclear</span>
      ) : null}
    </Badge>
  );
}
