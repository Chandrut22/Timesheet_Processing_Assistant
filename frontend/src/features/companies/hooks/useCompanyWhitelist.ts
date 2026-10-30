import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { companyKeys } from "../queries/companyQueries";
import { companyService } from "../services/companyService";
import type { WhitelistRead } from "../types/company";

export function useCompanyWhitelist(companyId: string): UseQueryResult<WhitelistRead[]> {
  return useQuery<WhitelistRead[]>({
    queryKey: companyKeys.whitelist(companyId),
    queryFn: () => companyService.listWhitelist(companyId),
  });
}
