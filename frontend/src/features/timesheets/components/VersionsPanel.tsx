// The timesheet's versions. A plain Save edits the current version; a reprocess or
// "Create as new version" keeps the earlier version here. A reviewer can look at one and restore it; the
// restored data becomes a NEW version and goes back to review (nothing is lost).
// Approve / reject are not versions: they are in the History panel.
import { History, RotateCcw } from "lucide-react";
import { useState, type JSX } from "react";
import { errorMessage } from "@/utils/errors";
import type { TimesheetChange, TimesheetRead, TimesheetVersionSummary } from "../types/timesheet";
import { Field, FormError } from "@/components/forms/Field";
import { Money } from "@/components/common/Money";
import { ErrorState } from "@/components/common/States";
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
import { formatDate, formatDateTime, formatHours, formatWeek, humanize } from "@/utils/format";
import { useRestoreVersion } from "../hooks/useTimesheetActions";
import { useTimesheetVersion, useTimesheetVersions } from "../hooks/useTimesheets";

/** What happened when the timesheet moved on from a version. */
const CHANGE_LABELS: Record<TimesheetChange, string> = {
  entries_edited: "Days edited as a new version",
  employee_matched: "Employee changed",
  week_changed: "Week changed as a new version",
  recalculated: "Pay recalculated",
  reprocessed: "Reprocessed",
  rolled_back: "Left when another version was restored",
};

export function VersionsPanel({
  t,
  readOnly,
}: {
  t: TimesheetRead;
  readOnly: boolean;
}): JSX.Element {
  const q = useTimesheetVersions(t.id);
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
            No earlier versions. Saving an edit changes this version. Reprocessing, or "Create as
            new version" when editing, keeps the version before it here.
          </p>
        ) : (
          <ol className="space-y-2">
            {q.data.map((v) => (
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
                    Then:{" "}
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

function VersionDays({ id, version }: { id: string; version: number }): JSX.Element {
  const q = useTimesheetVersion(id, version);
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
}): JSX.Element {
  const [reason, setReason] = useState("");
  const m = useRestoreVersion(t.id, version.version, {
    success: `Back on version ${version.version}. Version ${t.version} is kept.`,
    silentError: true,
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate(reason);
          }}
        >
          <DialogHeader>
            <DialogTitle>Restore version {version.version}?</DialogTitle>
            <DialogDescription>
              The timesheet becomes version {version.version} again: its days, employee, week, pay
              and flags come back, and it goes back to review. No new version is made. What version{" "}
              {t.version} has now is kept as version {t.version}, so you can switch back.
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
