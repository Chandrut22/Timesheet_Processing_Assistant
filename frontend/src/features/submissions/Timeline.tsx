import {
  ArrowRight,
  CircleCheck,
  CircleAlert,
  CircleDot,
  History,
  CircleX,
  ExternalLink,
} from "lucide-react";
import type {
  AuditEventRead,
  ProcessingStepRead,
  StateChangeRead,
  SubmissionTimeline,
} from "@/api/models";
import { SubmissionStateBadge } from "@/components/Badges";
import { JsonBlock } from "@/components/JsonBlock";
import { formatDateTime, formatDuration, humanize } from "@/lib/format";
import { traceUrl } from "@/lib/tracing";
import { cn } from "@/lib/utils";

type Item =
  | { kind: "state"; at: string; v: StateChangeRead }
  | { kind: "step"; at: string; v: ProcessingStepRead }
  | { kind: "audit"; at: string; v: AuditEventRead };

/** State changes, processing steps and decisions merged into one list, oldest first. */
export function Timeline({
  data,
  documentName,
}: {
  data: SubmissionTimeline;
  documentName: (id: string | null) => string | null;
}) {
  const items: Item[] = [
    ...data.states.map((v) => ({ kind: "state" as const, at: v.created_at, v })),
    ...data.steps.map((v) => ({ kind: "step" as const, at: v.created_at, v })),
    ...data.audit.map((v) => ({ kind: "audit" as const, at: v.created_at, v })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  if (items.length === 0)
    return <p className="text-sm text-muted-foreground">Nothing has happened yet.</p>;

  return (
    <ol className="relative space-y-3 border-l pl-5">
      {items.map((item) => (
        <li key={`${item.kind}-${item.v.id}`} className="relative">
          <Marker item={item} />
          {item.kind === "state" ? (
            <StateRow v={item.v} />
          ) : item.kind === "step" ? (
            <StepRow v={item.v} documentName={documentName(item.v.document_id)} />
          ) : (
            <AuditRow v={item.v} />
          )}
        </li>
      ))}
    </ol>
  );
}

function Marker({ item }: { item: Item }) {
  const base =
    "absolute -left-[29px] top-0.5 grid size-4 place-items-center rounded-full bg-card [&_svg]:size-4";
  if (item.kind === "state")
    return (
      <span className={cn(base, "text-primary")}>
        <CircleDot aria-hidden />
      </span>
    );
  if (item.kind === "audit")
    return (
      <span className={cn(base, "text-muted-foreground")}>
        <History aria-hidden />
      </span>
    );
  const r = item.v.result.toLowerCase();
  if (r === "ok" || r === "success" || r === "succeeded" || r === "done")
    return (
      <span className={cn(base, "text-emerald-600")}>
        <CircleCheck aria-hidden />
      </span>
    );
  if (r === "failed" || r === "error")
    return (
      <span className={cn(base, "text-red-600")}>
        <CircleX aria-hidden />
      </span>
    );
  return (
    <span className={cn(base, "text-amber-600")}>
      <CircleAlert aria-hidden />
    </span>
  );
}

function When({ at, extra }: { at: string; extra?: string | null }) {
  return (
    <p className="text-xs text-muted-foreground">
      {formatDateTime(at)}
      {extra ? ` · ${extra}` : ""}
    </p>
  );
}

function StateRow({ v }: { v: StateChangeRead }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5 text-sm">
        {v.from_state ? (
          <>
            <SubmissionStateBadge state={v.from_state} />
            <ArrowRight className="size-3.5 text-muted-foreground" aria-label="to" />
          </>
        ) : null}
        <SubmissionStateBadge state={v.to_state} />
      </div>
      {v.reason ? <p className="mt-1 text-sm">{v.reason}</p> : null}
      <When at={v.created_at} extra={v.actor_name ?? "System"} />
    </div>
  );
}

function StepRow({ v, documentName }: { v: ProcessingStepRead; documentName: string | null }) {
  const trace = traceUrl(v.trace_id);
  const hasInput = Object.keys(v.input ?? {}).length > 0;
  const hasOutput = Object.keys(v.output ?? {}).length > 0;
  return (
    <details className="group">
      <summary className="cursor-pointer list-none rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
        <p className="text-sm">
          <span className="font-medium">{humanize(v.step)}</span>
          <span className="text-muted-foreground"> · {humanize(v.result)}</span>
          <span className="ml-2 text-xs text-primary group-open:hidden">Show details</span>
          <span className="ml-2 hidden text-xs text-primary group-open:inline">Hide details</span>
        </p>
        {v.message ? <p className="text-sm text-muted-foreground">{v.message}</p> : null}
        <When
          at={v.created_at}
          extra={[formatDuration(v.duration_ms), documentName].filter(Boolean).join(" · ")}
        />
        {trace ? (
          <a
            href={trace}
            target="_blank"
            rel="noreferrer"
            className="mt-0.5 inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <ExternalLink className="size-3" aria-hidden /> Open trace
          </a>
        ) : null}
      </summary>
      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Input</p>
          {hasInput ? (
            <JsonBlock value={v.input} />
          ) : (
            <p className="text-xs text-muted-foreground">—</p>
          )}
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Output</p>
          {hasOutput ? (
            <JsonBlock value={v.output} />
          ) : (
            <p className="text-xs text-muted-foreground">—</p>
          )}
        </div>
        {v.error_details ? (
          <div className="lg:col-span-2">
            <p className="mb-1 text-xs font-medium text-red-700">Error details</p>
            <JsonBlock value={v.error_details} className="border-red-200 bg-red-50" />
          </div>
        ) : null}
      </div>
    </details>
  );
}

function AuditRow({ v }: { v: AuditEventRead }) {
  return (
    <div>
      <p className="text-sm">
        <span className="font-medium">{humanize(v.action)}</span>
      </p>
      <When at={v.created_at} extra={v.actor_name ?? "System"} />
      {Object.keys(v.details ?? {}).length > 0 ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-primary">Details</summary>
          <JsonBlock value={v.details} className="mt-1" />
        </details>
      ) : null}
    </div>
  );
}
