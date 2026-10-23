// The timesheet's versions: every data change (days, employee, week, pay, reprocess,
// rollback) keeps the earlier version. A reviewer can look at one and restore it; the
// restored data becomes a NEW version and goes back to review (nothing is lost).
// Approve / reject are not versions: they are in the History panel.
import { useQuery } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import type { TimesheetChange, TimesheetRead, TimesheetVersionSummary } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { Field, FormError } from "@/components/Field";
import { Money } from "@/components/Money";
import { ErrorState } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime, formatHours, formatWeek, humanize } from "@/lib/format";
import { useTimesheetMutation } from "./useTimesheetMutation";

const CHANGE_LABELS: Record<TimesheetChange, string> = {
  entries_edited: "Days edited",
  employee_matched: "Employee changed",
  week_changed: "Week changed",
  recalculated: "Pay recalculated",
  reprocessed: "Reprocessed",
  rolled_back: "Rolled back",
};

export function VersionsPanel({ t, readOnly }: { t: TimesheetRead; readOnly: boolean }) {
  const q = useQuery({
    queryKey: qk.timesheets.versions(t.id),
    queryFn: () => coreApi.listVersions(t.id),
  });
  const [open, setOpen] = useState<number | null>(null);
  const [restoring, setRestoring] = useState<TimesheetVersionSummary | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="size-4" aria-hidden /> Versions
        </CardTitle>
        <span className="text-sm text-muted-foreground tabular">v{t.version}</span>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Skeleton className="h-20" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : q.data.length <= 1 ? (
          <p className="text-sm text-muted-foreground">
            No earlier versions. Changing the days, employee, week or pay, or reprocessing, keeps
            the version before it here.
          </p>
        ) : (
          <ol className="space-y-2">
            {q.data.map((v, i) => (
              <li key={v.version} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Version {v.version}</span>
                  {v.current ? <Badge variant="info">Current</Badge> : null}
                  {v.status ? <Badge variant="muted">{humanize(v.status)}</Badge> : null}
                  <span className="ml-auto flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-expanded={open === v.version}
                      onClick={() => setOpen(open === v.version ? null : v.version)}
                    >
                      {open === v.version ? "Hide" : "View"}
                    </Button>
                    {!v.current && !readOnly ? (
                      <Button variant="outline" size="sm" onClick={() => setRestoring(v)}>
                        <RotateCcw /> Restore
                      </Button>
                    ) : null}
                  </span>
                </div>
                <p className="mt-1 text-muted-foreground">
                  {v.extracted_name ?? "Unknown name"} · week {formatWeek(v.week_start)} · {v.days}{" "}
                  {v.days === 1 ? "day" : "days"} · {formatHours(v.total_hours)} h ·{" "}
                  <Money amount={v.gross_amount} currency={t.currency} missingLabel="not priced" />
                </p>
                {!v.current && v.change ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Replaced by version {q.data[i - 1]?.version ?? v.version + 1}:{" "}
                    <span className="font-medium text-foreground">{CHANGE_LABELS[v.change]}</span>
                    {v.changed_by_name ? ` by ${v.changed_by_name}` : ""}
                    {v.changed_at ? `, ${formatDateTime(v.changed_at)}` : ""}
                    {v.reason ? ` — “${v.reason}”` : ""}
                  </p>
                ) : null}
                {open === v.version ? <VersionDays id={t.id} version={v.version} /> : null}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
      {restoring ? (
        <RestoreDialog t={t} version={restoring} onClose={() => setRestoring(null)} />
      ) : null}
    </Card>
  );
}

function VersionDays({ id, version }: { id: string; version: number }) {
  const q = useQuery({
    queryKey: qk.timesheets.version(id, version),
    queryFn: () => coreApi.getVersion(id, version),
    staleTime: Infinity, // a saved version never changes
  });
  if (q.isPending) return <Skeleton className="mt-2 h-16" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const v = q.data;
  return (
    <div className="mt-2 space-y-1">
      {v.entries.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No days{v.stated_total !== null ? ` (weekly total ${formatHours(v.stated_total)} h)` : ""}
          .
        </p>
      ) : (
        <table className="w-full text-xs">
          <caption className="sr-only">Days in version {version}</caption>
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="font-normal">Day</th>
              <th className="text-right font-normal">Hours</th>
              <th className="pl-3 font-normal">Note</th>
            </tr>
          </thead>
          <tbody>
            {v.entries.map((e) => (
              <tr key={e.work_date}>
                <td>
                  {formatDate(e.work_date)}
                  {e.is_holiday ? " · holiday" : ""}
                </td>
                <td className="tabular text-right">{formatHours(e.hours)}</td>
                <td className="pl-3 text-muted-foreground">{e.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-muted-foreground">
        Regular {formatHours(v.regular_hours)} · OT {formatHours(v.overtime_hours)} · DT{" "}
        {formatHours(v.double_time_hours)} · Holiday {formatHours(v.holiday_hours)}
        {v.flags.length ? ` · flags: ${v.flags.join(", ")}` : ""}
      </p>
    </div>
  );
}

function RestoreDialog({
  t,
  version,
  onClose,
}: {
  t: TimesheetRead;
  version: TimesheetVersionSummary;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const m = useTimesheetMutation(
    () => coreApi.restoreVersion(t.id, version.version, reason.trim()),
    {
      success: `Version ${version.version} restored as version ${t.version + 1}.`,
      silentError: true,
      onSuccess: onClose,
    },
  );
  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate(undefined);
          }}
        >
          <DialogHeader>
            <DialogTitle>Restore version {version.version}?</DialogTitle>
            <DialogDescription>
              Its days, employee, week, pay and flags come back as version {t.version + 1}, and the
              timesheet goes back to review. The current version {t.version} is kept, so this can be
              undone.
            </DialogDescription>
          </DialogHeader>
          <FormError message={m.error ? errorMessage(m.error) : null} />
          <Field label="Reason (optional)" htmlFor="restore-reason">
            <Textarea
              id="restore-reason"
              rows={2}
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" type="button" onClick={onClose} disabled={m.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={m.isPending}>
              {m.isPending ? "Restoring…" : `Restore version ${version.version}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
