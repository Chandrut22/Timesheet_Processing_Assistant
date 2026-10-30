import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { login, type SessionUser } from "@/services/session";
import type { MessageResponse } from "../types/auth";

import { authService } from "../services/authService";

// The sign-in and password-reset forms show their own errors inline (silentError), and
// await mutateAsync() so react-hook-form's isSubmitting stays true while it runs.

export type LoginVariables = { email: string; password: string };

export function useLogin(): UseMutationResult<SessionUser, unknown, LoginVariables> {
  return useMutation<SessionUser, unknown, LoginVariables>({
    mutationFn: ({ email, password }) => login(email, password),
    meta: { silentError: true },
  });
}

export function useForgotPassword(): UseMutationResult<MessageResponse, unknown, string> {
  return useMutation<MessageResponse, unknown, string>({
    mutationFn: (email) => authService.forgotPassword(email),
    meta: { silentError: true },
  });
}

export type ResetPasswordVariables = { email: string; code: string; newPassword: string };

export function useResetPassword(): UseMutationResult<
  MessageResponse,
  unknown,
  ResetPasswordVariables
> {
  return useMutation<MessageResponse, unknown, ResetPasswordVariables>({
    mutationFn: ({ email, code, newPassword }) =>
      authService.resetPassword(email, code, newPassword),
    meta: { silentError: true },
  });
}
