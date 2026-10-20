import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import type { TimesheetRead } from "@/api/models";
import { Field, FormError } from "@/components/Field";
import { Banner } from "@/components/States";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { useTimesheetMutation } from "./useTimesheetMutation";

const approveSchema = z.object({ notes: z.string().max(1000, "At most 1000 characters") });
const rejectSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(3, "Give a reason of at least 3 characters")
    .max(1000, "At most 1000 characters"),
});

export function ApproveDialog({
  t,
  open,
  onOpenChange,
}: {
  t: TimesheetRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<z.infer<typeof approveSchema>>({
    resolver: zodResolver(approveSchema),
    defaultValues: { notes: "" },
  });
  const m = useTimesheetMutation(
    (notes: string) => coreApi.approve(t.id, notes.trim() || undefined),
    {
      success: "Timesheet approved.",
      silentError: true,
      onSuccess: () => {
        form.reset();
        onOpenChange(false);
      },
    },
  );
  const high = t.flags.filter((f) => f.severity === "high").length;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) m.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v.notes))} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Approve timesheet</DialogTitle>
            <DialogDescription>
              It will be included in the next payroll export for this week.
            </DialogDescription>
          </DialogHeader>
          {high > 0 ? (
            <Banner tone="danger">
              This timesheet has {high} high-severity {high === 1 ? "flag" : "flags"}. Make sure
              you've checked
              {high === 1 ? " it" : " them"} before approving.
            </Banner>
          ) : null}
          {/* 409s ("already approved", "another timesheet for this week") are shown as the backend wrote them. */}
          <FormError message={m.error ? errorMessage(m.error) : null} />
          <Field
            label="Notes (optional)"
            htmlFor="approve-notes"
            error={form.formState.errors.notes?.message}
          >
            <Textarea id="approve-notes" rows={3} {...form.register("notes")} />
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

export function RejectDialog({
  t,
  open,
  onOpenChange,
}: {
  t: TimesheetRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<z.infer<typeof rejectSchema>>({
    resolver: zodResolver(rejectSchema),
    defaultValues: { reason: "" },
  });
  const m = useTimesheetMutation((reason: string) => coreApi.reject(t.id, reason.trim()), {
    success: "Timesheet rejected.",
    silentError: true,
    onSuccess: () => {
      form.reset();
      onOpenChange(false);
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) m.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v.reason))} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Reject timesheet</DialogTitle>
            <DialogDescription>
              The reason is saved with the timesheet and shown in its history.
            </DialogDescription>
          </DialogHeader>
          <FormError message={m.error ? errorMessage(m.error) : null} />
          <Field
            label="Reason"
            htmlFor="reject-reason"
            error={form.formState.errors.reason?.message}
          >
            <Textarea id="reject-reason" rows={3} autoFocus {...form.register("reason")} />
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
