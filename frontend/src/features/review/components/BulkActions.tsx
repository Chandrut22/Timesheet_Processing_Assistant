import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX } from "lucide-react";
import { useState, type JSX } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { type BulkResult, timesheetKeys } from "@/features/timesheets";
import { Field } from "@/components/forms/Field";
import { Banner } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { useBulkApprove, useBulkReject } from "@/features/review";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { humanize } from "@/utils/format";

type Kind = "approve" | "reject";

const approveSchema = z.object({ notes: z.string().max(1000, "At most 1000 characters") });
const rejectSchema = z.object({
  reason: z.string().trim().min(3, "Give a reason of at least 3 characters").max(1000),
});

/** The bar that appears when rows are selected in the review queue. */
export function BulkBar({
  selected,
  labelFor,
  onDone,
}: {
  selected: string[];
  labelFor: (id: string) => string;
  onDone: () => void;
}): JSX.Element | null {
  const [open, setOpen] = useState<Kind | null>(null);
  const [result, setResult] = useState<{ kind: Kind; data: BulkResult } | null>(null);
  const queryClient = useQueryClient();

  const finish = (kind: Kind, data: BulkResult): void => {
    setOpen(null);
    setResult({ kind, data });
    void queryClient.invalidateQueries({ queryKey: timesheetKeys.all });
    onDone();
  };

  if (selected.length === 0 && !result) return null;

  return (
    <>
      {selected.length > 0 ? (
        <div className="sticky bottom-4 z-20 mx-auto mt-4 flex w-fit flex-wrap items-center gap-3 rounded-lg border bg-card px-4 py-2.5 shadow-lg">
          <span className="text-sm font-medium tabular">{selected.length} selected</span>
          <Button size="sm" variant="success" onClick={() => setOpen("approve")}>
            <CircleCheck /> Approve
          </Button>
          <Button size="sm" variant="destructive" onClick={() => setOpen("reject")}>
            <CircleX /> Reject
          </Button>
          <Button size="sm" variant="ghost" onClick={onDone}>
            Clear
          </Button>
        </div>
      ) : null}

      <BulkApproveDialog
        open={open === "approve"}
        ids={selected}
        onOpenChange={(o) => setOpen(o ? "approve" : null)}
        onDone={(d) => finish("approve", d)}
      />
      <BulkRejectDialog
        open={open === "reject"}
        ids={selected}
        onOpenChange={(o) => setOpen(o ? "reject" : null)}
        onDone={(d) => finish("reject", d)}
      />
      <BulkResultDialog result={result} labelFor={labelFor} onClose={() => setResult(null)} />
    </>
  );
}

function BulkApproveDialog({
  open,
  ids,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  ids: string[];
  onOpenChange: (open: boolean) => void;
  onDone: (r: BulkResult) => void;
}): JSX.Element {
  const form = useForm<z.infer<typeof approveSchema>>({
    resolver: zodResolver(approveSchema),
    defaultValues: { notes: "" },
  });
  const m = useBulkApprove(ids, (result) => {
    form.reset();
    onDone(result);
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v.notes))} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Approve {ids.length} timesheets</DialogTitle>
            <DialogDescription>
              Each timesheet gets the same checks as a single approval. Ones that fail are listed
              with the reason; the rest still go through.
            </DialogDescription>
          </DialogHeader>
          <Banner tone="warning">
            Timesheets with high-severity flags are skipped. Open those and approve them one by one.
          </Banner>
          <Field
            label="Notes (optional)"
            htmlFor="bulk-notes"
            error={form.formState.errors.notes?.message}
          >
            <Textarea id="bulk-notes" rows={3} {...form.register("notes")} />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={m.isPending}>
              Cancel
            </Button>
            <Button type="submit" variant="success" disabled={m.isPending}>
              {m.isPending ? "Approving…" : "Approve"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BulkRejectDialog({
  open,
  ids,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  ids: string[];
  onOpenChange: (open: boolean) => void;
  onDone: (r: BulkResult) => void;
}): JSX.Element {
  const form = useForm<z.infer<typeof rejectSchema>>({
    resolver: zodResolver(rejectSchema),
    defaultValues: { reason: "" },
  });
  const m = useBulkReject(ids, (result) => {
    form.reset();
    onDone(result);
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v.reason))} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Reject {ids.length} timesheets</DialogTitle>
            <DialogDescription>The same reason is saved on every timesheet.</DialogDescription>
          </DialogHeader>
          <Field label="Reason" htmlFor="bulk-reason" error={form.formState.errors.reason?.message}>
            <Textarea id="bulk-reason" rows={3} autoFocus {...form.register("reason")} />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={m.isPending}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={m.isPending}>
              {m.isPending ? "Rejecting…" : "Reject"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BulkResultDialog({
  result,
  labelFor,
  onClose,
}: {
  result: { kind: Kind; data: BulkResult } | null;
  labelFor: (id: string) => string;
  onClose: () => void;
}): JSX.Element {
  const data = result?.data;
  return (
    <Dialog open={!!result} onOpenChange={(o) => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>
            {result?.kind === "approve" ? "Bulk approve" : "Bulk reject"}: results
          </DialogTitle>
          {data ? (
            <DialogDescription>
              {data.succeeded} of {data.requested} done
              {data.failed > 0 ? `, ${data.failed} not changed` : ""}.
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {data ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timesheet</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((r) => (
                <TableRow key={r.timesheet_id}>
                  <TableCell className="font-medium">{labelFor(r.timesheet_id)}</TableCell>
                  <TableCell>
                    {r.ok ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700">
                        <CircleCheck className="size-4" /> Done
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-700">
                        <CircleX className="size-4" /> Not changed
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">
                    {r.ok ? humanize(r.status) : (r.error ?? "—")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        <DialogFooter>
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
