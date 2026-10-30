import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { companyKeys } from "../queries/companyQueries";
import { companyService } from "../services/companyService";
import type { CompanyListParams } from "../types/company";

type CompaniesListData = Awaited<ReturnType<typeof companyService.listCompanies>>;

export function useCompaniesList(params: CompanyListParams): UseQueryResult<CompaniesListData> {
  return useQuery<CompaniesListData>({
    queryKey: companyKeys.list(params),
    queryFn: ({ signal }) => companyService.listCompanies(params, signal),
    placeholderData: keepPreviousData,
  });
}
