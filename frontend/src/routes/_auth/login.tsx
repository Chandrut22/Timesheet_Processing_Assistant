import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { errorMessage } from "@/api/errors";
import { login } from "@/api/session";
import { Field, FormError } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type LoginSearch = { redirect?: string };

export const Route = createFileRoute("/_auth/login")({
  validateSearch: (search: Record<string, unknown>): LoginSearch => {
    const r = search.redirect;
    return {
      redirect:
        typeof r === "string" && r.length <= 1000 && !r.startsWith("/login") ? r : undefined,
    };
  },
  component: LoginPage,
});

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

/** Only same-app paths, never another site ("//evil.com"). */
function safeRedirect(target: string | undefined): string {
  if (!target || !target.startsWith("/") || target.startsWith("//")) return "/";
  if (target.startsWith("/login")) return "/";
  return target;
}

function LoginPage() {
  const { redirect } = Route.useSearch();
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values.email.trim(), values.password);
      router.history.push(safeRedirect(redirect));
    } catch (err) {
      setFormError(errorMessage(err));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4">
      <div>
        <h1 className="text-lg font-semibold">Sign in</h1>
        <p className="text-sm text-muted-foreground">Use your work email and password.</p>
      </div>
      <FormError message={formError} />
      <Field label="Email" htmlFor="email" error={errors.email?.message}>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          aria-invalid={!!errors.email}
          {...form.register("email")}
        />
      </Field>
      <Field label="Password" htmlFor="password" error={errors.password?.message}>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          {...form.register("password")}
        />
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
      <Link to="/forgot-password" className="text-center text-sm text-primary hover:underline">
        Forgot your password?
      </Link>
    </form>
  );
}
