import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { authService } from "@/features/auth";
import { applyFieldErrors } from "@/lib/forms";

import type { PasswordValues } from "../schemas/passwordSchema";

type UseChangePasswordOptions = {
  setError: UseFormSetError<PasswordValues>;
  onSuccess: () => void;
};

export function useChangePassword({
  setError,
  onSuccess,
}: UseChangePasswordOptions): UseMutationResult<void, unknown, PasswordValues, unknown> {
  return useMutation<void, unknown, PasswordValues>({
    mutationFn: async (values) => {
      await authService.changePassword(values.current_password, values.new_password);
    },
    meta: { silentError: true },
    onSuccess,
    onError: (error) => applyFieldErrors(error, setError, ["current_password", "new_password"]),
  });
}
