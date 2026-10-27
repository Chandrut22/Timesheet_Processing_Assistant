import { Link } from "@tanstack/react-router";
import { OctagonAlert, CircleCheck, ClipboardCheck, MailWarning } from "lucide-react";
import type { ReactNode } from "react";
import { useUser } from "@/features/auth";
import { SourceIcon, SubmissionStateBadge } from "@/features/submissions";
import { MailLink } from "@/components/common/MailLink";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
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
// import { useDashboard, type StreamState } from "../hooks/useDashboard";
import { useDashboard } from "../hooks/useDashboard";

import { MailCheckButton } from "./MailCheckButton";
import { formatRelative } from "@/utils/format";
import { cn } from "@/lib/utils";

export function DashboardPage() {
  const user = useUser();
  const dash = useDashboard();
  const counts = dash.data?.counts;

  // StatCard takes { data, isPending, isError }; build that from the live snapshot.
  const stat = (value: number | undefined) => ({
    data: value,
    isPending: dash.isPending,
    isError: dash.isError && !dash.data,
  });

  return (
    <>
      <PageHeader
        title={`Hello, ${user.name.split(" ")[0]}`}
        description="What needs attention today."
      />

      <div className="mb-3 flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
        <MailCheckButton />
        {/* <LiveBadge state={dash.stream} /> */}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Needs review"
          query={stat(counts?.needs_review)}
          icon={<ClipboardCheck />}
          link={
            <Link to="/review" search={{ status: "needs_review" }}>
              Open review queue
            </Link>
          }
        />
        <StatCard
          label="High severity"
          query={stat(counts?.high_severity)}
          icon={<OctagonAlert />}
          tone="danger"
          link={
            <Link to="/review" search={{ status: "needs_review", severity: "high" }}>
              Review high severity
            </Link>
          }
        />
        <StatCard
          label="Approved, waiting for export"
          query={stat(counts?.approved_waiting_export)}
          icon={<CircleCheck />}
          tone="success"
          link={<Link to="/export">Go to payroll export</Link>}
        />
        <StatCard
          label="Failed emails"
          query={stat(counts?.failed_submissions)}
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
        {dash.isPending ? (
          <TableSkeleton rows={5} cols={4} />
        ) : dash.isError && !dash.data ? (
          <CardContent>
            <ErrorState error={dash.error} onRetry={() => void dash.refetch()} />
          </CardContent>
        ) : !dash.data || dash.data.recent.length === 0 ? (
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
              {dash.data.recent.map((s) => (
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
                    <MailLink url={s.mail_url}>{s.subject ?? "—"}</MailLink>
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

// function LiveBadge({ state }: { state: StreamState }) {
//   const live = state === "live";
//   return (
//     <span role="status" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
//       <span
//         className={cn(
//           "size-2 rounded-full",
//           live ? "bg-emerald-500" : "bg-amber-500 motion-safe:animate-pulse",
//         )}
//       />
//       {live ? "Live" : "Reconnecting…"}
//     </span>
//   );
// }
