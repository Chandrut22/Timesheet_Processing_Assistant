import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { OctagonAlert, CircleCheck, ClipboardCheck, MailWarning } from "lucide-react";
import type { ReactNode } from "react";
import { coreApi, type SubmissionListParams, type TimesheetListParams } from "@/api/core";
import { qk } from "@/api/queryKeys";
import { useIsAdmin, useUser } from "@/auth/useSession";
import { SourceIcon, SubmissionStateBadge } from "@/components/Badges";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/States";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/")({ component: DashboardPage });

function useTimesheetCount(params: TimesheetListParams, enabled = true) {
  const p = { ...params, size: 1, page: 1 };
  return useQuery({
    queryKey: qk.timesheets.list(p),
    queryFn: () => coreApi.listTimesheets(p),
    select: (d) => d.total,
    enabled,
  });
}

function useSubmissionCount(params: SubmissionListParams) {
  const p = { ...params, size: 1, page: 1 };
  return useQuery({
    queryKey: qk.submissions.list(p),
    queryFn: () => coreApi.listSubmissions(p),
    select: (d) => d.total,
  });
}

function DashboardPage() {
  const user = useUser();
  const isAdmin = useIsAdmin();
  const needsReview = useTimesheetCount({ status: ["needs_review"] });
  const high = useTimesheetCount({ status: ["needs_review"], severity: ["high"] });
  const approved = useTimesheetCount({ status: ["approved"] }, isAdmin);
  const failed = useSubmissionCount({ status: "failed" });
  const recentParams = { page: 1, size: 10 };
  const recent = useQuery({
    queryKey: qk.submissions.list(recentParams),
    queryFn: () => coreApi.listSubmissions(recentParams),
    refetchInterval: (q) =>
      q.state.data?.items.some((s) => s.status === "received" || s.status === "processing")
        ? 5000
        : false,
  });

  return (
    <>
      <PageHeader
        title={`Hello, ${user.name.split(" ")[0]}`}
        description="What needs attention today."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Needs review"
          query={needsReview}
          icon={<ClipboardCheck />}
          link={
            <Link to="/review" search={{ status: "needs_review" }}>
              Open review queue
            </Link>
          }
        />
        <StatCard
          label="High severity"
          query={high}
          icon={<OctagonAlert />}
          tone="danger"
          link={
            <Link to="/review" search={{ status: "needs_review", severity: "high" }}>
              Review high severity
            </Link>
          }
        />
        {isAdmin ? (
          <StatCard
            label="Approved, waiting for export"
            query={approved}
            icon={<CircleCheck />}
            tone="success"
            link={<Link to="/export">Go to payroll export</Link>}
          />
        ) : null}
        <StatCard
          label="Failed emails"
          query={failed}
          icon={<MailWarning />}
          tone="warning"
          link={
            <Link to="/submissions" search={{ status: "failed" }}>
              See failed submissions
            </Link>
          }
        />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Latest submissions</CardTitle>
          <Link to="/submissions" className="text-sm text-primary hover:underline">
            View all
          </Link>
        </CardHeader>
        {recent.isPending ? (
          <TableSkeleton rows={5} cols={4} />
        ) : recent.isError ? (
          <CardContent>
            <ErrorState error={recent.error} onRetry={() => void recent.refetch()} />
          </CardContent>
        ) : recent.data.items.length === 0 ? (
          <CardContent>
            <EmptyState title="No submissions yet" hint="Emails and uploads will appear here." />
          </CardContent>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>From</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.data.items.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <SourceIcon source={s.source} />
                  </TableCell>
                  <TableCell className="max-w-56 truncate">
                    <Link
                      to="/submissions/$submissionId"
                      params={{ submissionId: s.id }}
                      className="font-medium hover:underline"
                    >
                      {s.sender_email ?? s.uploaded_by_name ?? "—"}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-72 truncate text-muted-foreground">
                    {s.subject ?? "—"}
                  </TableCell>
                  <TableCell>
                    <SubmissionStateBadge state={s.state} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatRelative(s.received_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </>
  );
}

const TONES = {
  default: "text-primary bg-primary/10",
  danger: "text-red-700 bg-red-50",
  success: "text-emerald-700 bg-emerald-50",
  warning: "text-amber-700 bg-amber-50",
} as const;

function StatCard({
  label,
  query,
  icon,
  link,
  tone = "default",
}: {
  label: string;
  query: { data?: number; isPending: boolean; isError: boolean };
  icon: ReactNode;
  link: ReactNode;
  tone?: keyof typeof TONES;
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-4 pt-5">
        <span
          className={cn("grid size-10 place-items-center rounded-lg [&_svg]:size-5", TONES[tone])}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          {query.isPending ? (
            <Skeleton className="mt-1 h-8 w-16" />
          ) : query.isError ? (
            <p className="mt-1 text-sm text-destructive">Couldn't load</p>
          ) : (
            <p className="tabular mt-0.5 text-3xl font-semibold">{query.data}</p>
          )}
          <div className="mt-1 text-sm text-primary hover:underline">{link}</div>
        </div>
      </CardContent>
    </Card>
  );
}
