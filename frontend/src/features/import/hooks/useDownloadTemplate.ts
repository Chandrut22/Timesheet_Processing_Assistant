import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { importService } from "../services/importService";
import type { ImportResource } from "../types/import";

/** The empty .xlsx with the columns an import expects. A failure becomes a toast. */
export function useDownloadTemplate(
  resource: ImportResource,
): UseMutationResult<void, Error, void> {
  return useMutation({
    mutationFn: async () => {
      await importService.downloadTemplate(resource);
    },
  });
}
