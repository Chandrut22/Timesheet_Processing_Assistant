import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { importService } from "../services/importService";
import type { ImportReport, ImportResource, OnDuplicate, OnError } from "../types/import";

interface RunImportOptions {
  resource: ImportResource;
  file: File | null;
  onError: OnError;
  onDuplicate: OnDuplicate;
  onResult: (report: ImportReport) => void;
  onImported: (report: ImportReport) => void;
}

type ImportResult = Awaited<ReturnType<typeof importService.importFile>>;

export function useRunImport({
  resource,
  file,
  onError,
  onDuplicate,
  onResult,
  onImported,
}: RunImportOptions): UseMutationResult<ImportResult, Error, boolean> {
  return useMutation<ImportResult, Error, boolean>({
    mutationFn: (dryRun: boolean) => {
      if (!file) {
        throw new Error("Please select a file before importing.");
      }

      return importService.importFile(resource, file, {
        dryRun,
        onError,
        onDuplicate,
      });
    },
    meta: { silentError: true },
    onSuccess: (result) => {
      // Always display the result, including dry-run results.
      onResult(result);

      // Notify the parent only after a committed import.
      if (result.committed) {
        onImported(result);
      }
    },
  });
}
