// Bulk import for an admin list (users, employees, companies, holidays):
// pick a CSV / XLSX file -> "Check file" (a dry run: nothing is written, the report
// shows each row's fate) -> "Import" (the same file and options, for real).
import { useMutation } from "@tanstack/react-query";
import { Download, FileUp } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/services/apiErrors";
import { importService } from "../services/importService";
import type { ImportReport, ImportResource, OnDuplicate, OnError } from "../types/import";
import { Banner } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  NATURAL_KEY,
  ON_ERROR_OPTIONS,
  RESOURCE_LABEL,
  STATUS_BADGE,
  canCommit,
  onDuplicateOptions,
  rowProblems,
  summarize,
} from "../utils/importUtils";

export function ImportButton({
  resource,
  onImported,
}: {
  resource: ImportResource;
  onImported: (report: ImportReport) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <FileUp /> Import
      </Button>
      {open ? (
        <ImportDialog
          resource={resource}
          open={open}
          onOpenChange={setOpen}
          onImported={onImported}
        />
      ) : null}
    </>
  );
}

export function ImportDialog({
  resource,
  open,
  onOpenChange,
  onImported,
}: {
  resource: ImportResource;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (report: ImportReport) => void;
}) {
  const ids = useId();
  const label = RESOURCE_LABEL[resource];
  const [file, setFile] = useState<File | null>(null);
  const [onError, setOnError] = useState<OnError>("abort");
  const [onDuplicate, setOnDuplicate] = useState<OnDuplicate>("error");
  const [report, setReport] = useState<ImportReport | null>(null);

  // Any change to the file or the options makes the last check stale.
  const reset = () => setReport(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) =>
      importService.importFile(resource, file as File, { dryRun, onError, onDuplicate }),
    meta: { silentError: true }, // shown in the dialog
    onSuccess: (result) => {
      setReport(result);
      if (result.committed) {
        onImported(result);
        toast.success(summarize(result, resource));
      }
    },
  });

  const template = useMutation({
    mutationFn: () => importService.downloadTemplate(resource),
  });

  const done = report?.committed === true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>Import {label.many}</DialogTitle>
          <DialogDescription>
            A .csv or .xlsx file with the template's columns (first sheet only). Check it first:
            nothing is saved until you press Import.
            {resource === "users"
              ? " Each new user gets the welcome email with their password; leave the password blank for a random one."
              : null}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid min-w-0 flex-1 gap-1.5">
              <Label htmlFor={`${ids}-file`}>File (.csv or .xlsx)</Label>
              <Input
                id={`${ids}-file`}
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                disabled={run.isPending || done}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  reset();
                }}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => template.mutate()}
              disabled={template.isPending}
            >
              <Download /> {template.isPending ? "Downloading…" : "Download template"}
            </Button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor={`${ids}-on-error`}>If a row has a problem</Label>
              <NativeSelect
                id={`${ids}-on-error`}
                value={onError}
                disabled={run.isPending || done}
                onChange={(e) => {
                  setOnError(e.target.value as OnError);
                  reset();
                }}
              >
                {ON_ERROR_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${ids}-on-duplicate`}>
                If a {label.one} already exists ({NATURAL_KEY[resource]})
              </Label>
              <NativeSelect
                id={`${ids}-on-duplicate`}
                value={onDuplicate}
                disabled={run.isPending || done}
                onChange={(e) => {
                  setOnDuplicate(e.target.value as OnDuplicate);
                  reset();
                }}
              >
                {onDuplicateOptions(resource).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          {run.isError ? <Banner tone="danger">{errorMessage(run.error)}</Banner> : null}
          {report ? <ReportView report={report} resource={resource} /> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={run.isPending}>
            {done ? "Close" : "Cancel"}
          </Button>
          {done ? null : report && canCommit(report) ? (
            <Button onClick={() => run.mutate(false)} disabled={run.isPending}>
              {run.isPending
                ? "Importing…"
                : `Import ${(report.created + report.updated).toLocaleString()} ${
                    report.created + report.updated === 1 ? label.one : label.many
                  }`}
            </Button>
          ) : (
            <Button onClick={() => run.mutate(true)} disabled={!file || run.isPending}>
              {run.isPending ? "Checking…" : "Check file"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReportView({ report, resource }: { report: ImportReport; resource: ImportResource }) {
  const tone = report.committed
    ? "success"
    : report.failed
      ? report.on_error === "abort" || !report.dry_run
        ? "danger"
        : "warning"
      : "info";
  return (
    <div className="grid gap-3" aria-live="polite">
      <Banner tone={tone}>
        <p className="font-medium">{summarize(report, resource)}</p>
        {report.dry_run && report.failed && report.on_error === "abort" ? (
          <p className="mt-1">
            Fix those rows and check again, or choose “Import the good rows, skip the rest”.
          </p>
        ) : null}
        {report.dry_run && !report.failed && report.created + report.updated === 0 ? (
          <p className="mt-1">There is nothing new to import.</p>
        ) : null}
        {report.warnings.map((w) => (
          <p key={w} className="mt-1">
            {w}
          </p>
        ))}
      </Banner>
      {report.rows.length ? (
        <div className="max-h-72 overflow-y-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Row</TableHead>
                <TableHead className="w-28">Result</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.rows.map((row) => (
                <TableRow key={row.row}>
                  <TableCell className="tabular-nums">{row.row}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_BADGE[row.status]}>{row.status}</Badge>
                  </TableCell>
                  <TableCell className="whitespace-normal text-sm">
                    {rowProblems(row) || row.warnings.join(" ") || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {report.rows_omitted ? (
        <p className="text-sm text-muted-foreground">
          {report.rows_omitted.toLocaleString()} more rows are not listed (problems are listed
          first).
        </p>
      ) : null}
    </div>
  );
}
