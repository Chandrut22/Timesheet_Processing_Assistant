import { getRouteApi, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { CircleCheck, Search, CircleX } from "lucide-react";
import { useState, type ReactNode } from "react";
import { isApiError } from "@/services/apiErrors";
import type { TimesheetRead } from "../types/timesheet";
import { TimesheetStatusBadge } from "./TimesheetBadges";
import { MailLink } from "@/components/common/MailLink";
import { PageHeader } from "@/components/common/PageHeader";
import { Banner, BlockSkeleton, EmptyState, ErrorState } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApproveDialog, RejectDialog } from "./DecisionDialogs";
import { EntriesEditor } from "./EntriesEditor";
import { FlagsPanel } from "./FlagsPanel";
import { HandwritingBanner } from "./HandwritingBanner";
import { HistoryPanel } from "./HistoryPanel";
import { MatchEmployeeDialog } from "./MatchEmployeeDialog";
import { PayBreakdown } from "./PayBreakdown";
import { useTimesheetMutation } from "../hooks/useTimesheetMutation";
import { VersionsPanel } from "./VersionsPanel";
import { WeeklyTotalPanel } from "./WeeklyTotalPanel";
import { formatDateTime, formatHours, formatPercent, formatWeek, humanize } from "@/utils/format";
import { timesheetCompanyName, timesheetEmployeeName } from "../utils/names";
import { useCompanyMap } from "@/features/companies";
import { useEmployeeMap } from "@/features/employees";
import { hasFlag, isWeeklyTotal } from "../utils/severity";
import { submissionService, submissionKeys } from "@/features/submissions";
import { timesheetService } from "../services/timesheetService";
import { timesheetKeys } from "../queries/timesheetQueries";
import { BackButton } from "@/components/common/BackButton";

const routeApi = getRouteApi("/_app/timesheets/$timesheetId");

const READ_ONLY = new Set(["exported"]);

export function TimesheetPage() {
  const { timesheetId } = routeApi.useParams();
  const q = useQuery({
    queryKey: timesheetKeys.detail(timesheetId),
    queryFn: () => timesheetService.getTimesheet(timesheetId),
  });

  const back = <BackButton fallback="/review" fallbackLabel="Review queue" />;

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

  const recalc = useTimesheetMutation(() => timesheetService.recalculate(t.id), {
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
      <HandwritingBanner t={t} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {isWeeklyTotal(t) ? (
            <WeeklyTotalPanel
              key={t.week_start ?? ""}
              t={t}
              weekStartDay={t.company_id ? companies.get(t.company_id)?.week_start : undefined}
              readOnly={readOnly}
            />
          ) : null}
          <EntriesEditor key={JSON.stringify(t.entries)} timesheet={t} readOnly={readOnly} />
          {showCompare ? <ComparePanel t={t} /> : null}
          <VersionsPanel t={t} readOnly={readOnly} />
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
    queryKey: submissionKeys.detail(t.submission_id),
    queryFn: () => submissionService.getSubmission(t.submission_id),
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
            <dd className="min-w-0 break-words">
              <MailLink url={q.data.mail_url}>{q.data.subject ?? "—"}</MailLink>
            </dd>
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
