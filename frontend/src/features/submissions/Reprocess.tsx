import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { coreApi } from "@/api/core";
import { errorMessage, isApiError } from "@/api/errors";
import type { ReprocessRunRead, SubmissionRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { Field, FormError } from "@/components/Field";
import { JsonBlock } from "@/components/JsonBlock";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { formatDateTime, humanize } from "@/lib/format";

const schema = z.object({
  reason: z
    .string()
    .trim()
    .min(3, "Say why, in at least 3 characters")
    .max(1000, "At most 1000 characters"),
  document_id: z.string(),
});
type Values = z.infer<typeof schema>;

export function ReprocessDialog({
  submission,
  open,
  onOpenChange,
}: {
  submission: SubmissionRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "", document_id: "" },
  });
  // Set when the backend answers 409 confirmation_required: some timesheets are
  // already approved. Its message says which; the reviewer can go back, or send
  // the same request again with confirm_approved: true.
  const [confirm, setConfirm] = useState<{ message: string; values: Values } | null>(null);
  const m = useMutation({
    mutationFn: ({ v, confirmApproved }: { v: Values; confirmApproved: boolean }) =>
      coreApi.reprocess(submission.id, v.reason.trim(), v.document_id || null, confirmApproved),
    meta: { silentError: true },
    onError: (err, { v }) => {
      if (isApiError(err, 409) && err.code === "confirmation_required") {
        setConfirm({ message: errorMessage(err), values: v });
      }
    },
    onSuccess: () => {
      setConfirm(null);
      toast.success(
        "Reprocessing queued. Each timesheet keeps its earlier version in its history.",
      );
      form.reset();
      onOpenChange(false);
      void queryClient.invalidateQueries({ queryKey: qk.submissions.all });
      void queryClient.invalidateQueries({ queryKey: qk.timesheets.all });
    },
  });

  const needsConfirm = confirm !== null;
  // Any other error (other 409s: already queued, submission ignored) is shown as the backend wrote it.
  const otherError =
    m.error && !(isApiError(m.error, 409) && m.error.code === "confirmation_required")
      ? errorMessage(m.error)
      : null;

  const close = (o: boolean) => {
    if (!o) {
      m.reset();
      setConfirm(null);
    }
    onOpenChange(o);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <form
          onSubmit={form.handleSubmit((v) => m.mutate({ v, confirmApproved: false }))}
          className="grid gap-4"
        >
          <DialogHeader>
            <DialogTitle>Reprocess</DialogTitle>
            <DialogDescription>
              Run it again with the current companies, employees and rules. The timesheets are
              updated in place and nothing is lost: each one keeps its earlier version in its
              history, so it can be rolled back.
            </DialogDescription>
          </DialogHeader>

          {confirm ? (
            <div
              role="alert"
              className="grid gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-900"
            >
              <p>{confirm.message}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={m.isPending}
                  onClick={() => m.mutate({ v: confirm.values, confirmApproved: true })}
                >
                  {m.isPending ? "Replacing…" : "Replace anyway"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={m.isPending}
                  onClick={() => {
                    m.reset();
                    setConfirm(null);
                  }}
                >
                  Go back
                </Button>
              </div>
            </div>
          ) : null}
          <FormError message={otherError} />

          <fieldset disabled={needsConfirm || m.isPending} className="grid gap-4">
            <Field label="What to reprocess" htmlFor="rp-doc">
              <NativeSelect id="rp-doc" {...form.register("document_id")}>
                <option value="">
                  The whole {submission.source === "upload" ? "upload" : "email"}
                </option>
                {submission.documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    Only {d.filename}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field
              label="Reason"
              htmlFor="rp-reason"
              error={form.formState.errors.reason?.message}
              hint="e.g. Employee list updated: added John Mathew (SYN-EMP-020)"
            >
              <Textarea id="rp-reason" rows={3} autoFocus {...form.register("reason")} />
            </Field>
          </fieldset>
          <DialogFooter>
            <Button variant="outline" onClick={() => close(false)} disabled={m.isPending}>
              Cancel
            </Button>
            {!needsConfirm ? (
              <Button type="submit" disabled={m.isPending}>
                {m.isPending ? "Queuing…" : "Reprocess"}
              </Button>
            ) : null}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const RUN_TONE: Record<string, BadgeVariant> = {
  queued: "secondary",
  pending: "secondary",
  running: "info",
  completed: "success",
  succeeded: "success",
  done: "success",
  failed: "danger",
};

export function ReprocessRuns({
  runs,
  documentName,
}: {
  runs: ReprocessRunRead[];
  documentName: (id: string | null) => string | null;
}) {
  if (runs.length === 0)
    return <p className="text-sm text-muted-foreground">This hasn't been reprocessed.</p>;
  return (
    <ul className="space-y-3">
      {[...runs]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((r) => (
          <li key={r.id} className="rounded-md border p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={RUN_TONE[r.status] ?? "secondary"}>{humanize(r.status)}</Badge>
              <span className="font-medium">{r.requested_by_name}</span>
              <span className="text-muted-foreground">· {formatDateTime(r.created_at)}</span>
              {r.completed_at ? (
                <span className="text-muted-foreground">
                  · finished {formatDateTime(r.completed_at)}
                </span>
              ) : null}
              <span className="text-muted-foreground">
                ·{" "}
                {r.document_id
                  ? `only ${documentName(r.document_id) ?? "one document"}`
                  : "whole submission"}
              </span>
            </div>
            <p className="mt-1 text-sm">“{r.reason}”</p>
            {r.error ? <p className="mt-1 text-sm text-red-700">{r.error}</p> : null}
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-primary">Before and after</summary>
              <div className="mt-2 grid gap-2 lg:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Before</p>
                  <JsonBlock value={r.before_result} />
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">After</p>
                  {r.after_result ? (
                    <JsonBlock value={r.after_result} />
                  ) : (
                    <p className="text-xs text-muted-foreground">Not finished yet.</p>
                  )}
                </div>
              </div>
            </details>
          </li>
        ))}
    </ul>
  );
}
