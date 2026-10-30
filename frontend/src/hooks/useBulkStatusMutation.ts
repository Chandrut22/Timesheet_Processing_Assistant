import {
  type QueryKey,
  type UseMutationResult,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import type { BulkDeleteResult, BulkStatusResult } from "@/types/api";
import type { BulkAction } from "@/utils/rowSelection";

export type BulkStatusMutationVariables = {
  action: BulkAction;
  ids: string[];
};

type BulkStatusMutationResult = BulkStatusResult | BulkDeleteResult;

type UseBulkStatusMutationOptions = {
  setStatus: (ids: string[], isActive: boolean) => Promise<BulkStatusResult>;
  remove?: (ids: string[]) => Promise<BulkDeleteResult>;
  invalidate: QueryKey[];
  onSuccess?: (result: BulkStatusMutationResult, variables: BulkStatusMutationVariables) => void;
};

export function useBulkStatusMutation({
  setStatus,
  remove,
  invalidate,
  onSuccess,
}: UseBulkStatusMutationOptions): UseMutationResult<
  BulkStatusMutationResult,
  unknown,
  BulkStatusMutationVariables
> {
  const queryClient = useQueryClient();

  return useMutation<BulkStatusMutationResult, unknown, BulkStatusMutationVariables>({
    mutationFn: ({ action, ids }): Promise<BulkStatusMutationResult> => {
      if (action === "delete" && remove) {
        return remove(ids);
      }

      return setStatus(ids, action === "activate");
    },

    onSuccess: (result, variables) => {
      for (const key of invalidate) {
        void queryClient.invalidateQueries({ queryKey: key });
      }

      onSuccess?.(result, variables);
    },
  });
}
