import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useCallback } from "react";

import type { BulkStatusApi } from "@/hooks/useBulkStatusMutation";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { userKeys } from "../queries/userQueries";
import { userService } from "../services/userService";
import type { UserCreate, UserListParams, UserRead, UserUpdate } from "../types/user";

type UserPage = Awaited<ReturnType<typeof userService.listUsers>>;

export const userBulkStatus: BulkStatusApi = {
  setStatus: userService.bulkUserStatus,
  invalidate: [userKeys.all],
};

export function useUsersList(params: UserListParams): UseQueryResult<UserPage> {
  return useQuery({
    queryKey: userKeys.list(params),
    queryFn: ({ signal }) => userService.listUsers(params, signal),
    placeholderData: keepPreviousData,
  });
}

/** After an import from Excel: show the new users. */
export function useRefreshUsers(): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: userKeys.all });
  }, [queryClient]);
}

export type UpdateUserVariables = { id: string; body: UserUpdate };

/** Change a role or activate / deactivate. The backend refuses changing your own role
 * or demoting the last admin; its message is shown in a toast (the shared handler). */
export function useUpdateUser(
  opts: MutationCallbacks<UserRead, UpdateUserVariables> = {},
): UseMutationResult<UserRead, Error, UpdateUserVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: UpdateUserVariables) => userService.updateUser(id, body),
    onSuccess: (u, v) => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
      opts.onSuccess?.(u, v);
    },
  });
}

/** The dialog shows the error itself. */
export function useCreateUser(
  opts: MutationCallbacks<UserRead, UserCreate> = {},
): UseMutationResult<UserRead, Error, UserCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreate) => userService.createUser(body),
    meta: { silentError: true },
    onSuccess: (u, body) => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
      opts.onSuccess?.(u, body);
    },
    onError: (error, variables) => opts.onError?.(error, variables),
  });
}

/** An admin sets someone's password. The dialog shows the error itself. */
export function useSetUserPassword(
  userId: string,
  opts: MutationCallbacks<void, string> = {},
): UseMutationResult<void, Error, string> {
  return useMutation({
    mutationFn: async (newPassword: string) => {
      await userService.setUserPassword(userId, newPassword);
    },
    meta: { silentError: true },
    onSuccess: (_, newPassword) => opts.onSuccess?.(undefined, newPassword),
    onError: (error, variables) => opts.onError?.(error, variables),
  });
}
