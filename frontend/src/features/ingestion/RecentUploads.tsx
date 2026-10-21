// The latest uploads (from everyone: the API has no "uploaded by me" filter, so each row
// says who uploaded it). Refreshes every 5 s while one of them is still being processed,
// and not at all while the browser tab is hidden.
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { coreApi, type SubmissionListParams } from "@/api/core";
import type { SubmissionRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { SubmissionStateBadge } from "@/components/Badges";
import { ErrorState } from "@/components/States";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/format";
import { useCompanyMap } from "@/lib/lookups";
import { IN_PROGRESS_STATES } from "@/lib/submissionStates";
import { cn } from "@/lib/utils";

const RECENT_UPLOADS: SubmissionListParams = { source: "upload", page: 1, size: 5 };
const POLL_MS = 5000;

function fileSummary(s: SubmissionRead): { label: string; title: string } {
  const names = s.documents.map((d) => d.filename);
  if (names.length === 0) return { label: "No files", title: "" };
  const more = names.length > 1 ? ` +${names.length - 1} more` : "";
  return { label: `${names[0]}${more}`, title: names.join("\n") };
}

export function RecentUploads({ className }: { className?: string }) {
  const companies = useCompanyMap();
  const recent = useQuery({
    queryKey: qk.submissions.recentUploads(RECENT_UPLOADS),
    queryFn: () => coreApi.listSubmissions(RECENT_UPLOADS),
    refetchInterval: (q) =>
      q.state.data?.items.some((s) => IN_PROGRESS_STATES.has(s.state)) ? POLL_MS : false,
    refetchIntervalInBackground: false, // a hidden tab does not poll
  });

  return (
    <Card className={cn("flex min-h-0 flex-col overflow-hidden", className)}>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b px-5 py-3">
        <h2 className="text-sm font-semibold">Recent uploads</h2>
        <Link
          to="/submissions"
          search={{ source: "upload" }}
          className="text-sm text-primary hover:underline"
        >
          View all
        </Link>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {recent.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading recent uploads">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : recent.isError ? (
          <ErrorState
            error={recent.error}
            onRetry={() => void recent.refetch()}
            className="m-4 py-6"
          />
        ) : recent.data.items.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">
            No uploads yet. Files you upload appear here.
          </p>
        ) : (
          <ul className="divide-y">
            {recent.data.items.map((s) => {
              const files = fileSummary(s);
              const company = s.company_id ? companies.get(s.company_id)?.name : undefined;
              return (
                <li key={s.id}>
                  <Link
                    to="/submissions/$submissionId"
                    params={{ submissionId: s.id }}
                    className="block space-y-1 px-5 py-3 hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="min-w-0 truncate text-sm font-medium" title={files.title}>
                        {files.label}
                      </span>
                      <SubmissionStateBadge state={s.state} />
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {company ?? "Company not set"}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      Uploaded by {s.uploaded_by_name ?? "someone"} ·{" "}
                      {formatRelative(s.received_at)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}
