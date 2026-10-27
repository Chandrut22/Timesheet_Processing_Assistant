import { useQuery } from "@tanstack/react-query";
// import { JsonBlock } from "@/components/common/JsonBlock";
import { ErrorState } from "@/components/common/States";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, humanize } from "@/utils/format";
import { auditService, auditKeys } from "@/features/audit";

export function HistoryPanel({
  entityType,
  entityId,
}: {
  entityType: "timesheet" | "submission";
  entityId: string;
}) {
  const q = useQuery({
    queryKey: auditKeys.entity(entityType, entityId),
    queryFn: () => auditService.listAuditEvents(entityType, entityId),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Skeleton className="h-20" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : q.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
        ) : (
          <ol className="relative space-y-3 border-l pl-4">
            {[...q.data]
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .map((e) => (
                <li key={e.id} className="text-sm">
                  <span
                    className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full border-2 border-card bg-primary"
                    aria-hidden
                  />
                  <p>
                    <span className="font-medium">{humanize(e.action)}</span>
                    <span className="text-muted-foreground"> · {e.actor_name ?? "System"}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">{formatDateTime(e.created_at)}</p>
                  {Object.keys(e.details ?? {}).length > 0 ? (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-primary">Details</summary>
                      {/* <JsonBlock value={e.details} className="mt-1" /> */}
                    </details>
                  ) : null}
                </li>
              ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
