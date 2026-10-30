import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useCallback } from "react";

import { employeeKeys } from "@/features/employees";
import type { BulkStatusApi } from "@/hooks/useBulkStatusMutation";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { companyKeys } from "../queries/companyQueries";
import { companyService } from "../services/companyService";
import type { CompanyCreate, CompanyRead, CompanyUpdate, WhitelistRead } from "../types/company";

/** Activate / deactivate companies (deactivating also deactivates their employees). */
export const companyBulkStatus: BulkStatusApi = {
  setStatus: companyService.bulkCompanyStatus,
  invalidate: [companyKeys.all, employeeKeys.all],
};

/** After an import from Excel: show the new companies. */
export function useRefreshCompanies(): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: companyKeys.all });
  }, [queryClient]);
}

/** The form shows the error itself. */
export function useCreateCompany(
  opts: MutationCallbacks<CompanyRead, CompanyCreate> = {},
): UseMutationResult<CompanyRead, Error, CompanyCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyCreate) => companyService.createCompany(body),
    meta: { silentError: true },
    onSuccess: (c, body) => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.all });
      opts.onSuccess?.(c, body);
    },
  });
}

/** The form shows the error itself. */
export function useUpdateCompany(
  companyId: string,
  opts: MutationCallbacks<CompanyRead, CompanyUpdate> = {},
): UseMutationResult<CompanyRead, Error, CompanyUpdate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyUpdate) => companyService.updateCompany(companyId, body),
    meta: { silentError: true },
    onSuccess: (c, body) => {
      queryClient.setQueryData(companyKeys.detail(c.id), c);
      void queryClient.invalidateQueries({ queryKey: companyKeys.all });
      opts.onSuccess?.(c, body);
    },
  });
}

/** The tab shows the error itself. */
export function useAddWhitelist(
  companyId: string,
  opts: MutationCallbacks<WhitelistRead, string> = {},
): UseMutationResult<WhitelistRead, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: string) => companyService.addWhitelist(companyId, value),
    meta: { silentError: true },
    onSuccess: (entry, value) => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.whitelist(companyId) });
      opts.onSuccess?.(entry, value);
    },
  });
}

export function useRemoveWhitelist(
  companyId: string,
  opts: MutationCallbacks<void, WhitelistRead> = {},
): UseMutationResult<void, Error, WhitelistRead> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entry: WhitelistRead) => companyService.removeWhitelist(companyId, entry.id),
    onSuccess: (_, entry) => {
      void queryClient.invalidateQueries({ queryKey: companyKeys.whitelist(companyId) });
      opts.onSuccess?.(undefined, entry);
    },
  });
}
