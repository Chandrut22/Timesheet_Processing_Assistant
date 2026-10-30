import { z } from "zod";

export const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z.string().min(8, "At least 8 characters").max(128, "At most 128 characters"),
    confirm: z.string(),
  })
  .refine((values) => values.new_password === values.confirm, {
    path: ["confirm"],
    message: "The passwords don't match",
  })
  .refine((values) => values.new_password !== values.current_password, {
    path: ["new_password"],
    message: "Choose a password different from the current one",
  });

export type PasswordValues = z.infer<typeof passwordSchema>;
