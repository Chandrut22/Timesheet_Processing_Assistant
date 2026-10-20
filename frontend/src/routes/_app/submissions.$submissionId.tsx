import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { coreApi } from "@/api/core";
import { isApiError } from "@/api/errors";
import type { SubmissionRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import {
  FlagBadges,
  IN_PROGRESS_STATES,
  SeverityDot,
  SourceIcon,
  SubmissionStateBadge,
  SubmissionStatusBadge,
  TimesheetStatusBadge,
} from "@/components/Badges";
import { Money } from "@/components/Money";
import { PageHeader } from "@/components/PageHeader";
import { Banner, BlockSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ReprocessDialog, ReprocessRuns } from "@/features/submissions/Reprocess";
import { describeReadLimit } from "@/features/submissions/readLimit";
import { Timeline } from "@/features/submissions/Timeline";
import { formatBytes, formatDateTime, formatHours, formatTime, formatWeek, humanize } from "@/lib/format";
import { timesheetEmployeeName, useCompanyMap, useEmployeeMap } from "@/lib/lookups";

export const Route = createFileRoute("/_app/submissions/$submissionId")({
  component: SubmissionDetailPage,
});

function isBusy(s: SubmissionRead) {
  return s.status === "received" || s.status === "processing" || IN_PROGRESS_STATES.has(s.state);
}

function SubmissionDetailPage() {
  const { submissionId } = Route.useParams();
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const timeline = useQuery({
    queryKey: qk.submissions.timeline(submissionId),
    queryFn: () => coreApi.getTimeline(submissionId),
    refetchInterval: (q) => (q.state.data && isBusy(q.state.data.submission) ? 3000 : false),
  });
  const busy = timeline.data ? isBusy(timeline.data.submission) : false;
  const tsParams = { submission_id: submissionId, include_superseded: true, size: 100, sort: "employee" as const, order: "asc" as const };
  const timesheets = useQuery({
    queryKey: qk.timesheets.list(tsParams),
    queryFn: () => coreApi.listTimesheets(tsParams),
    refetchInterval: busy ? 3000 : false,
  });
  const companies = useCompanyMap();
  const employees = useEmployeeMap((timesheets.data?.items ?? []).map((t) => t.company_id));

  // Polling stops the moment the timeline says processing is done, and the last
  // timesheet fetch can be up to 3 s older than that. Fetch once more on the
  // busy -> done change so the final timesheets appear without a reload.
  const queryClient = useQueryClient();
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy) {
      void queryClient.invalidateQueries({ queryKey: ["timesheets", "list"] });
      void queryClient.invalidateQueries({ queryKey: ["submissions", "list"] });
    }
    wasBusy.current = busy;
  }, [busy, queryClient]);

  const back = (
    <Link to="/submissions" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Submissions
    </Link>
  );

  if (timeline.isPending) {
    return (
      <>
        <PageHeader title="Submission" back={back} />
        <BlockSkeleton className="h-72" />
      </>
    );
  }
  if (timeline.isError) {
    return (
      <>
        <PageHeader title="Submission" back={back} />
        {isApiError(timeline.error, 404) ? (
          <EmptyState title="Submission not found" />
        ) : (
          <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} />
        )}
      </>
    );
  }

  const s = timeline.data.submission;
  const docName = (id: string | null) => (id ? (s.documents.find((d) => d.id === id)?.filename ?? null) : null);
  const company = s.company_id ? companies.get(s.company_id)?.name : null;

  return (
    <>
      <PageHeader
        back={back}
        title={
          <span className="flex items-center gap-2">
            <SourceIcon source={s.source} />
            {s.subject || (s.source === "upload" ? "Upload" : "(no subject)")}
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{s.sender_email ?? s.uploaded_by_name ?? "—"}</span>
            <span aria-hidden>·</span>
            <span>{formatDateTime(s.received_at)}</span>
            {company ? (
              <>
                <span aria-hidden>·</span>
                <span>{company}</span>
              </>
            ) : null}
            <SubmissionStateBadge state={s.state} />
          </span>
        }
        actions={
          <Button variant="outline" onClick={() => setReprocessOpen(true)} disabled={busy}>
            <RefreshCw /> Reprocess
          </Button>
        }
      />

      {busy ? (
        <Banner tone="info" className="mb-4">
          Processing… this page updates by itself.
        </Banner>
      ) : null}
      {s.retry_at ? (
        <Banner tone="warning" className="mb-4">
          Something went wrong; retrying at {formatTime(s.retry_at)} (attempt {s.attempts}).
        </Banner>
      ) : null}
      {s.error ? (
        <Banner tone="danger" className="mb-4">
          {s.error}
        </Banner>
      ) : null}
      {s.state_reason && !s.error ? (
        <Banner tone="info" className="mb-4">
          {s.state_reason}
        </Banner>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Timesheets from this submission</CardTitle>
            </CardHeader>
            {timesheets.isPending ? (
              <TableSkeleton rows={3} cols={6} />
            ) : timesheets.isError ? (
              <CardContent>
                <ErrorState error={timesheets.error} onRetry={() => void timesheets.refetch()} />
              </CardContent>
            ) : timesheets.data.items.length === 0 ? (
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  {busy ? "None yet: still processing." : "No timesheets were produced."}
                </p>
              </CardContent>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Employee</TableHead>
                    <TableHead>Week</TableHead>
                    <TableHead className="text-right">Hours</TableHead>
                    <TableHead className="text-right">Gross</TableHead>
                    <TableHead>Flags</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {timesheets.data.items.map((t) => {
                    const e = timesheetEmployeeName(t, employees);
                    return (
                      <TableRow key={t.id} className={t.status === "superseded" ? "opacity-60" : undefined}>
                        <TableCell>
                          <SeverityDot severity={t.severity} />
                        </TableCell>
                        <TableCell>
                          <Link
                            to="/timesheets/$timesheetId"
                            params={{ timesheetId: t.id }}
                            className="font-medium hover:underline"
                          >
                            {e.matched ? e.name : `Unmatched: «${e.name}»`}
                          </Link>
                          {t.version > 1 ? <span className="ml-1 text-xs text-muted-foreground">v{t.version}</span> : null}
                        </TableCell>
                        <TableCell>{formatWeek(t.week_start)}</TableCell>
                        <TableCell className="tabular text-right">{formatHours(t.total_hours)}</TableCell>
                        <TableCell className="text-right">
                          <Money amount={t.gross_amount} currency={t.currency} />
                        </TableCell>
                        <TableCell className="whitespace-normal">
                          <FlagBadges flags={t.flags} max={2} />
                        </TableCell>
                        <TableCell>
                          <TimesheetStatusBadge status={t.status} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
              <span className="text-xs text-muted-foreground">Oldest first · open a step to see its input and output</span>
            </CardHeader>
            <CardContent>
              <Timeline data={timeline.data} documentName={docName} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
              <span className="text-sm text-muted-foreground tabular">{s.documents.length}</span>
            </CardHeader>
            <CardContent>
              {s.documents.length === 0 ? (
                <p className="text-sm text-muted-foreground">No attachments.</p>
              ) : (
                <ul className="space-y-2">
                  {s.documents.map((d) => (
                    <li key={d.id} className="rounded-md border p-2.5 text-sm">
                      <div className="flex items-start justify-between gap-2">
                        <span className="min-w-0 font-medium break-words">{d.filename}</span>
                        <Badge variant={d.error ? "danger" : "secondary"}>{humanize(d.status)}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {d.content_type} · {formatBytes(d.size_bytes)}
                      </p>
                      <ReadLimitNote limit={d.read_limit} />
                      {d.error ? <p className="mt-1 text-xs text-red-700">{d.error}</p> : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Processing</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">Status</dt>
                <dd>
                  <SubmissionStatusBadge status={s.status} />
                </dd>
                <dt className="text-muted-foreground">Attempts</dt>
                <dd className="tabular">{s.attempts}</dd>
                <dt className="text-muted-foreground">Processed</dt>
                <dd>{formatDateTime(s.processed_at)}</dd>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reprocess runs</CardTitle>
            </CardHeader>
            <CardContent>
              <ReprocessRuns runs={timeline.data.reprocess_runs} documentName={docName} />
            </CardContent>
          </Card>
        </div>
      </div>

      <ReprocessDialog submission={s} open={reprocessOpen} onOpenChange={setReprocessOpen} />
    </>
  );
}

/** "Large file: Read pages 1–50 of 100" when only part of a document was read. */
function ReadLimitNote({ limit }: { limit: unknown }) {
  const text = describeReadLimit(limit);
  if (!text) return null;
  return <p className="mt-1 text-xs font-medium text-amber-800">Large file: {text}</p>;
}
