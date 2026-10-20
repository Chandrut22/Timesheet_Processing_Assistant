import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, Search, CircleX } from "lucide-react";
import { useState, type ReactNode } from "react";
import { coreApi } from "@/api/core";
import { isApiError } from "@/api/errors";
import type { TimesheetRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { TimesheetStatusBadge } from "@/components/Badges";
import { PageHeader } from "@/components/PageHeader";
import { Banner, BlockSkeleton, EmptyState, ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApproveDialog, RejectDialog } from "@/features/timesheet/DecisionDialogs";
import { EntriesEditor } from "@/features/timesheet/EntriesEditor";
import { FlagsPanel } from "@/features/timesheet/FlagsPanel";
import { HistoryPanel } from "@/features/timesheet/HistoryPanel";
import { MatchEmployeeDialog } from "@/features/timesheet/MatchEmployeeDialog";
import { PayBreakdown } from "@/features/timesheet/PayBreakdown";
import { useTimesheetMutation } from "@/features/timesheet/useTimesheetMutation";
import { formatDateTime, formatHours, formatPercent, formatWeek, humanize } from "@/lib/format";
import {
  timesheetCompanyName,
  timesheetEmployeeName,
  useCompanyMap,
  useEmployeeMap,
} from "@/lib/lookups";
import { hasFlag } from "@/lib/severity";

export const Route = createFileRoute("/_app/timesheets/$timesheetId")({
  component: TimesheetDetailPage,
});

const READ_ONLY = new Set(["exported", "superseded"]);

function TimesheetDetailPage() {
  const { timesheetId } = Route.useParams();
  const q = useQuery({
    queryKey: qk.timesheets.detail(timesheetId),
    queryFn: () => coreApi.getTimesheet(timesheetId),
  });

  const back = (
    <Link
      to="/review"
      className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Review queue
    </Link>
  );

  if (q.isPending) {
    return (
      <>
        <PageHeader title="Timesheet" back={back} />
        <div className="grid gap-4 lg:grid-cols-3">
          <BlockSkeleton className="h-64 lg:col-span-2" />
          <BlockSkeleton className="h-64" />
        </div>
      </>
    );
  }
  if (q.isError) {
    return (
      <>
        <PageHeader title="Timesheet" back={back} />
        {isApiError(q.error, 404) ? (
          <EmptyState
            title="Timesheet not found"
            hint="It may have been replaced, or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        )}
      </>
    );
  }
  return <TimesheetDetail t={q.data} back={back} />;
}

function TimesheetDetail({ t, back }: { t: TimesheetRead; back: ReactNode }) {
  const [dialog, setDialog] = useState<"approve" | "reject" | "match" | null>(null);
  const companies = useCompanyMap();
  const employees = useEmployeeMap([t.company_id]);
  const employee = timesheetEmployeeName(t, employees);
  const company = timesheetCompanyName(t, companies);
  const readOnly = READ_ONLY.has(t.status);

  const recalc = useTimesheetMutation(() => coreApi.recalculate(t.id), {
    success: "Recalculated with the company's current rules and rates.",
  });

  const showCompare = hasFlag(t.flags, "conflicting_hours", "total_mismatch");

  return (
    <>
      <PageHeader
        back={back}
        title={
          employee.matched ? (
            employee.name
          ) : (
            <span>
              <span className="text-amber-800">Unmatched:</span> «{employee.name}»
            </span>
          )
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{company}</span>
            <span aria-hidden>·</span>
            <span>Week {formatWeek(t.week_start)}</span>
            <TimesheetStatusBadge status={t.status} />
          </span>
        }
        actions={
          !readOnly ? (
            <>
              <Button variant="outline" onClick={() => setDialog("match")}>
                <Search /> {employee.matched ? "Change employee" : "Match employee"}
              </Button>
              {t.status !== "rejected" ? (
                <Button variant="destructive" onClick={() => setDialog("reject")}>
                  <CircleX /> Reject
                </Button>
              ) : null}
              {t.status !== "approved" ? (
                <Button variant="success" onClick={() => setDialog("approve")}>
                  <CircleCheck /> Approve
                </Button>
              ) : null}
            </>
          ) : null
        }
      />

      <StatusBanner t={t} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <EntriesEditor key={JSON.stringify(t.entries)} timesheet={t} readOnly={readOnly} />
          {showCompare ? <ComparePanel t={t} /> : null}
          <HistoryPanel entityType="timesheet" entityId={t.id} />
        </div>
        <div className="space-y-4">
          <FlagsPanel flags={t.flags} />
          <PayBreakdown
            t={t}
            readOnly={readOnly}
            recalculating={recalc.isPending}
            onRecalculate={() => recalc.mutate(undefined)}
          />
          <DetailsPanel t={t} employeeCode={employee.code} />
          <SourcePanel t={t} />
        </div>
      </div>

      {!readOnly ? (
        <>
          <ApproveDialog
            t={t}
            open={dialog === "approve"}
            onOpenChange={(o) => setDialog(o ? "approve" : null)}
          />
          <RejectDialog
            t={t}
            open={dialog === "reject"}
            onOpenChange={(o) => setDialog(o ? "reject" : null)}
          />
          {dialog === "match" ? (
            <MatchEmployeeDialog t={t} open onOpenChange={(o) => setDialog(o ? "match" : null)} />
          ) : null}
        </>
      ) : null}
    </>
  );
}

function StatusBanner({ t }: { t: TimesheetRead }) {
  if (t.status === "superseded") {
    return (
      <Banner tone="warning" className="mb-4">
        This version was replaced when the submission was reprocessed. It's kept for the record and
        can't be changed.{" "}
        {t.superseded_by_id ? (
          <Link
            to="/timesheets/$timesheetId"
            params={{ timesheetId: t.superseded_by_id }}
            className="font-medium underline"
          >
            Open the current version
          </Link>
        ) : null}
      </Banner>
    );
  }
  if (t.status === "exported") {
    return (
      <Banner tone="info" className="mb-4">
        Exported to payroll. It can no longer be edited, approved or rejected.
      </Banner>
    );
  }
  if (t.status === "approved" || t.status === "rejected") {
    return (
      <Banner tone={t.status === "approved" ? "success" : "danger"} className="mb-4">
        {humanize(t.status)}
        {t.reviewed_by_name ? ` by ${t.reviewed_by_name}` : ""}
        {t.reviewed_at ? ` on ${formatDateTime(t.reviewed_at)}` : ""}.
        {t.notes ? <span className="mt-1 block">“{t.notes}”</span> : null}
      </Banner>
    );
  }
  return null;
}

function ComparePanel({ t }: { t: TimesheetRead }) {
  const items = [
    { label: "Stated in the email", value: t.email_stated_total },
    { label: "Stated on the sheet", value: t.stated_total },
    { label: "Sum of the days", value: t.total_hours },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Hours don't agree</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 sm:grid-cols-3">
          {items.map((i) => (
            <div key={i.label} className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">{i.label}</dt>
              <dd className="tabular mt-1 text-xl font-semibold">
                {i.value === null || i.value === undefined ? "—" : `${formatHours(i.value)} h`}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function DetailsPanel({ t, employeeCode }: { t: TimesheetRead; employeeCode: string | null }) {
  const rows: [string, ReactNode][] = [
    ["Employee code", employeeCode ?? "—"],
    ["Name on the sheet", t.extracted_name ?? "—"],
    ["Code on the sheet", t.extracted_code ?? "—"],
    ["Company on the sheet", t.extracted_company_name ?? "—"],
    ["Match", t.match_method ? humanize(t.match_method) : "—"],
    ["Why", t.match_reason ?? "—"],
    ["Confidence", formatPercent(t.confidence)],
    ["Reading confidence", formatPercent(t.read_confidence)],
    ["Version", String(t.version)],
    ["Created", formatDateTime(t.created_at)],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Details</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="min-w-0 break-words">{v}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function SourcePanel({ t }: { t: TimesheetRead }) {
  const q = useQuery({
    queryKey: qk.submissions.detail(t.submission_id),
    queryFn: () => coreApi.getSubmission(t.submission_id),
  });
  const doc = q.data?.documents.find((d) => d.id === t.document_id);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Source</CardTitle>
        <Link
          to="/submissions/$submissionId"
          params={{ submissionId: t.submission_id }}
          className="text-sm text-primary hover:underline"
        >
          Timeline
        </Link>
      </CardHeader>
      <CardContent className="text-sm">
        {q.isPending ? (
          <BlockSkeleton className="h-16" />
        ) : q.isError ? (
          <p className="text-muted-foreground">Couldn't load the submission.</p>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted-foreground">
              {q.data.source === "upload" ? "Uploaded by" : "From"}
            </dt>
            <dd className="min-w-0 break-words">
              {q.data.sender_email ?? q.data.uploaded_by_name ?? "—"}
            </dd>
            <dt className="text-muted-foreground">Subject</dt>
            <dd className="min-w-0 break-words">{q.data.subject ?? "—"}</dd>
            <dt className="text-muted-foreground">Received</dt>
            <dd>{formatDateTime(q.data.received_at)}</dd>
            <dt className="text-muted-foreground">Document</dt>
            <dd className="min-w-0 break-words">{doc?.filename ?? "—"}</dd>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
