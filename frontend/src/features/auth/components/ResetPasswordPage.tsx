import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type JSX } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { errorMessage } from "@/services/apiErrors";
import { Field, FormError } from "@/components/forms/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/lib/forms";
import { authService } from "../services/authService";

const routeApi = getRouteApi("/_auth/reset-password");

type ResetSearch = { email?: string };

const schema = z
  .object({
    email: z.email("Enter a valid email address"),
    code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code from the email"),
    new_password: z.string().min(8, "At least 8 characters").max(128, "At most 128 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "The passwords don't match",
  });
type Values = z.infer<typeof schema>;

export function ResetPasswordPage(): JSX.Element {
  const { email } = routeApi.useSearch();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: email ?? "", code: "", new_password: "", confirm: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (v) => {
    setFormError(null);
    try {
      const res = await authService.resetPassword(v.email.trim(), v.code, v.new_password);
      toast.success(res.message || "Your password has been changed. Sign in with the new one.");
      await navigate({ to: "/login" });
    } catch (err) {
      if (!applyFieldErrors(err, form.setError, ["email", "code", "new_password"])) {
        setFormError(errorMessage(err));
      }
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4">
      <div>
        <h1 className="text-lg font-semibold">Reset password</h1>
        <p className="text-sm text-muted-foreground">
          Enter the code from the email. Three wrong codes lock resets for 30 minutes.
        </p>
      </div>
      <FormError message={formError} />
      <Field label="Email" htmlFor="email" error={errors.email?.message}>
        <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
      </Field>
      <Field label="6-digit code" htmlFor="code" error={errors.code?.message}>
        <Input
          id="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          className="tabular tracking-[0.4em]"
          {...form.register("code")}
        />
      </Field>
      <Field label="New password" htmlFor="new_password" error={errors.new_password?.message}>
        <Input
          id="new_password"
          type="password"
          autoComplete="new-password"
          {...form.register("new_password")}
        />
      </Field>
      <Field label="Confirm new password" htmlFor="confirm" error={errors.confirm?.message}>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          {...form.register("confirm")}
        />
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Saving…" : "Set new password"}
      </Button>
      <Link to="/login" className="text-center text-sm text-primary hover:underline">
        Back to sign in
      </Link>
    </form>
  );
}

/** The page's search params, checked when the URL changes. */
export const validateResetPasswordSearch = (search: Record<string, unknown>): ResetSearch => ({
  email: typeof search.email === "string" ? search.email : undefined,
});
