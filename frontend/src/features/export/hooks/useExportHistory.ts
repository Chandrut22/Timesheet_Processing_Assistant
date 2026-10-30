import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { exportKeys } from "../queries/exportQueries";
import { exportService } from "../services/exportService";

type ExportListParams = Parameters<typeof exportService.listExports>[0];

type ExportListData = Awaited<ReturnType<typeof exportService.listExports>>;

export function useExportHistory(params: ExportListParams): UseQueryResult<ExportListData> {
  return useQuery<ExportListData>({
    queryKey: exportKeys.list(params),
    queryFn: () => exportService.listExports(params),
    placeholderData: keepPreviousData,
  });
}
