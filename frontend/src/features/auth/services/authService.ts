import { http } from "@/lib/axios";
import { responseOf, checked } from "@/services/response";
import { PrincipalReadSchema } from "@/services/schemas";
import { MessageResponseSchema } from "../types/auth";

export const authService = {
  me: () => checked(PrincipalReadSchema, http.get("/api/me")),
  forgotPassword: (email: string) =>
    http.post("/auth/forgot-password", { email }).then(responseOf(MessageResponseSchema)),
  resetPassword: (email: string, code: string, newPassword: string) =>
    http
      .post("/auth/reset-password", { email, code, new_password: newPassword })
      .then(responseOf(MessageResponseSchema)),
  changePassword: (currentPassword: string, newPassword: string) =>
    http
      .post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .then(() => undefined),
};
