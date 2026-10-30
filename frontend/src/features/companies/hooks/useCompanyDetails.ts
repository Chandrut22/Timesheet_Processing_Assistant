import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { companyKeys } from "../queries/companyQueries";
import { companyService } from "../services/companyService";
import type { CompanyRead } from "../types/company";

export function useCompanyDetails(companyId: string): UseQueryResult<CompanyRead> {
  return useQuery<CompanyRead>({
    queryKey: companyKeys.detail(companyId),
    queryFn: () => companyService.getCompany(companyId),
  });
}
