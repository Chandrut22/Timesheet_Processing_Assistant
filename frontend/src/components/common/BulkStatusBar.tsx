// Tick boxes and the bar for activating, deactivating or deleting many rows at once
// (admins only). Each row is handled on its own by the backend: the ones that fail stay
// ticked and their reasons are listed; the rest still go through.
import { type QueryKey, useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleX, Power, PowerOff, Trash2 } from "lucide-react";
import { type ReactNode, useState, type JSX } from "react";
import { toast } from "sonner";
import type { BulkDeleteResult, BulkStatusResult } from "@/types/api";
import { Banner } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type BulkAction,
  type BulkRow,
  failedIds,
  resultSummary,
  wouldChange,
} from "@/utils/rowSelection";
import type { RowSelection } from "@/hooks/useRowSelection";

type Noun = { one: string; many: string };

const SHOWN_NAMES = 10;
const LABELS: Record<BulkAction, string> = {
  activate: "Activate",
  deactivate: "Deactivate",
  delete: "Delete",
};

/** The box in the table header: ticks every selectable row on this page. */
export function SelectAllCheckbox({ selection }: { selection: RowSelection }): JSX.Element {
  return (
    <Checkbox
      aria-label="Select all on this page"
      checked={selection.header === "all"}
      ref={(el) => {
        if (el) el.indeterminate = selection.header === "some";
      }}
      disabled={!selection.hasSelectable}
      onChange={selection.toggleAll}
    />
  );
}

/** The box at the start of a row. Shift-click ticks every row since the last click. */
export function RowCheckbox({
  row,
  selection,
}: {
  row: BulkRow;
  selection: RowSelection;
}): JSX.Element {
  return (
    <Checkbox
      aria-label={`Select ${row.label}`}
      checked={selection.selected.has(row.id)}
      disabled={row.disabled}
      title={row.disabled ? row.disabledReason : undefined}
      // React reports a checkbox change with the click that caused it, so shift is there.
      onChange={(e) => {
        const ev = e.nativeEvent as Partial<MouseEvent>;
        selection.toggle(row.id, ev.shiftKey === true);
      }}
    />
  );
}

/** "1 of the selected is already inactive and stays as it is." */
function alreadyNote(n: number, active: boolean): string {
  const state = active ? "active" : "inactive";
  return n === 1
    ? `1 of the selected is already ${state} and stays as it is.`
    : `${n} of the selected are already ${state} and stay as they are.`;
}

type Outcome = { action: BulkAction; failures: { id: string; label: string; error: string }[] };

export function BulkStatusBar({
  selection,
  noun,
  setStatus,
  remove,
  invalidate,
  warnings = {},
}: {
  selection: RowSelection;
  noun: Noun;
  setStatus: (ids: string[], isActive: boolean) => Promise<BulkStatusResult>;
  /** Offer "Delete" too (holidays). */
  remove?: (ids: string[]) => Promise<BulkDeleteResult>;
  /** Lists to refresh afterwards. */
  invalidate: QueryKey[];
  /** What the confirm dialog warns about, per action. */
  warnings?: Partial<Record<BulkAction, ReactNode>>;
}): JSX.Element | null {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<BulkAction | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const rows = selection.selectedRows;

  const m = useMutation({
    mutationFn: ({
      action,
      ids,
    }: {
      action: BulkAction;
      ids: string[];
    }): Promise<BulkStatusResult | BulkDeleteResult> =>
      action === "delete" && remove ? remove(ids) : setStatus(ids, action === "activate"),
    onSuccess: (result, { action, ids }) => {
      for (const key of invalidate) void queryClient.invalidateQueries({ queryKey: key });
      const summary = resultSummary(result, action, noun);
      setConfirming(null);
      const failed = failedIds(result);
      if (failed.size === 0) {
        toast.success(summary);
        selection.clear();
        return;
      }
      toast.warning(summary);
      const labels = new Map(rows.map((r) => [r.id, r.label]));
      selection.set(ids.filter((id) => failed.has(id)));
      setOutcome({
        action,
        failures: result.results
          .filter((r) => !r.ok)
          .map((r) => ({
            id: r.id,
            label: labels.get(r.id) ?? r.id,
            error: r.error ?? "Not changed.",
          })),
      });
    },
  });

  if (rows.length === 0 && !outcome) return null;

  const affected = confirming
    ? confirming === "delete"
      ? rows
      : rows.filter((r) => r.isActive !== (confirming === "activate"))
    : [];
  const count = (n: number): string => `${n} ${n === 1 ? noun.one : noun.many}`;

  return (
    <>
      {rows.length > 0 ? (
        <div
          role="toolbar"
          aria-label={`Change the selected ${noun.many}`}
          className="sticky bottom-4 z-20 mx-auto mt-4 flex w-fit flex-wrap items-center gap-3 rounded-lg border bg-card px-4 py-2.5 shadow-lg"
        >
          <span className="text-sm font-medium tabular" aria-live="polite">
            {rows.length} selected
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={wouldChange(rows, "activate") === 0 || m.isPending}
            title={wouldChange(rows, "activate") === 0 ? "All of them are active" : undefined}
            onClick={() => setConfirming("activate")}
          >
            <Power /> Activate
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={wouldChange(rows, "deactivate") === 0 || m.isPending}
            title={wouldChange(rows, "deactivate") === 0 ? "All of them are inactive" : undefined}
            onClick={() => setConfirming("deactivate")}
          >
            <PowerOff /> Deactivate
          </Button>
          {remove ? (
            <Button
              size="sm"
              variant="destructive"
              disabled={m.isPending}
              onClick={() => setConfirming("delete")}
            >
              <Trash2 /> Delete
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={selection.clear}>
            Clear
          </Button>
        </div>
      ) : null}

      <Dialog
        open={confirming !== null}
        onOpenChange={(o) => !o && !m.isPending && setConfirming(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirming ? `${LABELS[confirming]} ${count(affected.length)}?` : ""}
            </DialogTitle>
            {confirming && affected.length < rows.length ? (
              <DialogDescription>
                {alreadyNote(rows.length - affected.length, confirming === "activate")}
              </DialogDescription>
            ) : null}
          </DialogHeader>
          <ul className="grid gap-0.5 text-sm" aria-label={`The ${noun.many} that change`}>
            {affected.slice(0, SHOWN_NAMES).map((r) => (
              <li key={r.id} className="truncate">
                {r.label}
              </li>
            ))}
            {affected.length > SHOWN_NAMES ? (
              <li className="text-muted-foreground">and {affected.length - SHOWN_NAMES} more</li>
            ) : null}
          </ul>
          {confirming && warnings[confirming] ? (
            <Banner tone="warning">{warnings[confirming]}</Banner>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(null)} disabled={m.isPending}>
              Cancel
            </Button>
            <Button
              variant={confirming === "activate" ? "default" : "destructive"}
              disabled={m.isPending || affected.length === 0}
              onClick={() =>
                confirming && m.mutate({ action: confirming, ids: affected.map((r) => r.id) })
              }
            >
              {m.isPending ? "Working…" : confirming ? LABELS[confirming] : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!outcome} onOpenChange={(o) => !o && setOutcome(null)}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>
              {outcome ? `${count(outcome.failures.length)} not changed` : ""}
            </DialogTitle>
            <DialogDescription>
              The rest went through. These stay selected so you can fix them and try again.
            </DialogDescription>
          </DialogHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{noun.one[0]?.toUpperCase() + noun.one.slice(1)}</TableHead>
                <TableHead>Why</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {outcome?.failures.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-medium">
                    <span className="inline-flex items-center gap-1">
                      <CircleX className="size-4 text-red-700" /> {f.label}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">
                    {f.error}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <DialogFooter>
            <Button onClick={() => setOutcome(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
