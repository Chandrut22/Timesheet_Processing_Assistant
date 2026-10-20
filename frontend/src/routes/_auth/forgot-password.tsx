import { createFileRoute, Link } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { authApi } from "@/api/auth";
import { errorMessage } from "@/api/errors";
import { Field, FormError } from "@/components/Field";
import { Banner } from "@/components/States";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const Route = createFileRoute("/_auth/forgot-password")({
  component: ForgotPasswordPage,
});

const schema = z.object({ email: z.email("Enter a valid email address") });
type Values = z.infer<typeof schema>;

// The same message is shown whether or not the email has an account.
const SENT_MESSAGE =
  "If an account exists for that email, we've sent a 6-digit code. It may take a minute to arrive.";

function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ email }) => {
    setFormError(null);
    try {
      await authApi.forgotPassword(email.trim());
      setSentTo(email.trim());
    } catch (err) {
      setFormError(errorMessage(err)); // e.g. 429 "Try again in N seconds"
    }
  });

  if (sentTo) {
    return (
      <div className="grid gap-4">
        <h1 className="text-lg font-semibold">Check your email</h1>
        <Banner tone="success">{SENT_MESSAGE}</Banner>
        <Button asChild>
          <Link to="/reset-password" search={{ email: sentTo }}>
            I have a code
          </Link>
        </Button>
        <Link to="/login" className="text-center text-sm text-primary hover:underline">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4">
      <div>
        <h1 className="text-lg font-semibold">Forgot password</h1>
        <p className="text-sm text-muted-foreground">We'll email you a 6-digit code to reset it.</p>
      </div>
      <FormError message={formError} />
      <Field label="Email" htmlFor="email" error={errors.email?.message}>
        <Input id="email" type="email" autoComplete="email" autoFocus {...form.register("email")} />
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Sending…" : "Send code"}
      </Button>
      <Link to="/login" className="text-center text-sm text-primary hover:underline">
        Back to sign in
      </Link>
    </form>
  );
}
