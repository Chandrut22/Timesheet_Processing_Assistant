import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { CompanyRead } from "../types/company";
import { LOOKUP_STALE } from "@/config/constants";
import { companyService } from "../services/companyService";
import { companyKeys } from "../queries/companyQueries";

/** All companies (first 100, active and inactive), for selects and name lookups. */
export function useCompanies() {
  return useQuery({
    queryKey: companyKeys.lookup,
    queryFn: () => companyService.listCompanies({ size: 100, page: 1 }),
    staleTime: LOOKUP_STALE,
    select: (page) => page.items,
  });
}

export function useCompanyMap(): Map<string, CompanyRead> {
  const { data } = useCompanies();
  return useMemo(() => new Map((data ?? []).map((c) => [c.id, c])), [data]);
}
