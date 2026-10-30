import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { exportKeys } from "../queries/exportQueries";
import { exportService } from "../services/exportService";
import type { ExportPreview } from "../types/export";

export function useExportPreview(companyId: string, week: string): UseQueryResult<ExportPreview> {
  return useQuery<ExportPreview>({
    queryKey: exportKeys.preview(companyId, week),
    queryFn: () => exportService.previewExport(companyId, week),
    placeholderData: keepPreviousData,
  });
}
