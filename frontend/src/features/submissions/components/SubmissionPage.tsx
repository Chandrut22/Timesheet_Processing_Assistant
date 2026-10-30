import { getRouteApi, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type JSX } from "react";
import { toast } from "sonner";
import { isApiError } from "@/services/apiErrors";
import {
  FlagBadges,
  MatchAction,
  MatchEmployeeDialog,
  nextUnmatched,
  SeverityDot,
  TimesheetStatusBadge,
  timesheetEmployeeName,
} from "@/features/timesheets";
import {
  WritingClassChip,
  SourceIcon,
  SubmissionStateBadge,
  SubmissionStatusBadge,
} from "./SubmissionBadges";
import { Money } from "@/components/common/Money";
import { MailLink } from "@/components/common/MailLink";
import { PageHeader } from "@/components/common/PageHeader";
import {
  Banner,
  BlockSkeleton,
  EmptyState,
  ErrorState,
  TableSkeleton,
} from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ReprocessDialog, ReprocessRuns } from "./Reprocess";
import { describeReadLimit } from "../utils/readLimit";
import { Timeline } from "./Timeline";
import {
  formatBytes,
  formatDateTime,
  formatHours,
  formatTime,
  formatWeek,
  humanize,
} from "@/utils/format";
import { useCompanyMap } from "@/features/companies";
import { useEmployeeMap } from "@/features/employees";
import { BackButton } from "@/components/common/BackButton";
import { useSubmissionTimesheets } from "../hooks/useSubmissionTimesheets";
import { isSubmissionBusy, useSubmissionTimeline } from "../hooks/useSubmissionTimeline";

const routeApi = getRouteApi("/_app/submissions/$submissionId");

export function SubmissionPage(): JSX.Element {
  const { submissionId } = routeApi.useParams();
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const timeline = useSubmissionTimeline(submissionId);
  const busy = timeline.data ? isSubmissionBusy(timeline.data.submission) : false;
  const timesheets = useSubmissionTimesheets(submissionId, busy);
  const companies = useCompanyMap();
  const employees = useEmployeeMap((timesheets.data?.items ?? []).map((t) => t.company_id));

  // "Match employee" on a timesheet of this submission (followed by id across refreshes).
  const [matchingId, setMatchingId] = useState<string | null>(null);
  const tsItems = timesheets.data?.items ?? [];
  const matching = matchingId ? tsItems.find((t) => t.id === matchingId) : undefined;
  const matchNext = matching ? nextUnmatched(tsItems, matching.id) : null;

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

  const back = <BackButton fallback="/submissions" fallbackLabel="Submissions" />;

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
  const docName = (id: string | null): string | null =>
    id ? (s.documents.find((d) => d.id === id)?.filename ?? null) : null;
  const company = s.company_id ? companies.get(s.company_id)?.name : null;

  return (
    <>
      <PageHeader
        back={back}
        title={
          <span className="flex items-center gap-2">
            <SourceIcon source={s.source} />
            <MailLink url={s.mail_url}>
              {s.subject || (s.source === "upload" ? "Upload" : "(no subject)")}
            </MailLink>
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
                      <TableRow key={t.id} className="group">
                        <TableCell>
                          <SeverityDot severity={t.severity} />
                        </TableCell>
                        <TableCell>
                          <Link
                            to="/timesheets/$timesheetId"
                            params={{ timesheetId: t.id }}
                            className="font-medium hover:underline"
                          >
                            {e.matched ? (
                              e.name
                            ) : (
                              <span className="text-amber-800">Unmatched: «{e.name}»</span>
                            )}
                          </Link>
                          {t.version > 1 ? (
                            <span className="ml-1 text-xs text-muted-foreground">v{t.version}</span>
                          ) : null}
                          {e.code ? (
                            <span className="block text-xs text-muted-foreground">{e.code}</span>
                          ) : null}
                          <MatchAction
                            t={t}
                            name={e.name}
                            onMatch={() => setMatchingId(t.id)}
                            disabled={busy}
                          />
                        </TableCell>
                        <TableCell>{formatWeek(t.week_start)}</TableCell>
                        <TableCell className="tabular text-right">
                          {formatHours(t.total_hours)}
                        </TableCell>
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
              <span className="text-xs text-muted-foreground">
                Oldest first · open a step to see its input and output
              </span>
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
                        <Badge
                          variant={
                            d.skipped_by_classifier ? "warning" : d.error ? "danger" : "secondary"
                          }
                        >
                          {d.skipped_by_classifier ? "Not read" : humanize(d.status)}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {d.content_type} · {formatBytes(d.size_bytes)}
                      </p>
                      {d.read_method === "vision" ? (
                        <div className="mt-1">
                          <WritingClassChip doc={d} />
                        </div>
                      ) : null}
                      <ReadLimitNote limit={d.read_limit} />
                      {d.error ? (
                        <p
                          className={`mt-1 text-xs ${d.skipped_by_classifier ? "text-amber-800" : "text-red-700"}`}
                        >
                          {d.error}
                        </p>
                      ) : null}
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
      {matching ? (
        <MatchEmployeeDialog
          key={matching.id}
          t={matching}
          open
          onOpenChange={(o) => {
            if (!o) setMatchingId(null);
          }}
          onMatchNext={() => {
            if (matchNext) {
              setMatchingId(matchNext.id);
            } else {
              setMatchingId(null);
              toast.success("All unmatched timesheets in this submission are done.");
            }
          }}
        />
      ) : null}
    </>
  );
}

/** "Large file: Read pages 1–50 of 100" when only part of a document was read. */
function ReadLimitNote({ limit }: { limit: unknown }): JSX.Element | null {
  const text = describeReadLimit(limit);
  if (!text) return null;
  return <p className="mt-1 text-xs font-medium text-amber-800">Large file: {text}</p>;
}
