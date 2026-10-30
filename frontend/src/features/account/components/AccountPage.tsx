import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import type { JSX } from "react";

import { Field, FormError } from "@/components/forms/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useUser } from "@/features/auth";
import { passwordSchema, useChangePassword, type PasswordValues } from "@/features/account";
import { errorMessage } from "@/services/apiErrors";

export function AccountPage(): JSX.Element {
  const user = useUser();

  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm: "",
    },
  });

  const m = useChangePassword({
    setError: form.setError,
    onSuccess: () => {
      toast.success("Password changed.");
      form.reset();
    },
  });

  const e = form.formState.errors;

  return (
    <>
      <PageHeader title="My account" />

      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>

          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Name</dt>
              <dd>{user.name}</dd>

              <dt className="text-muted-foreground">Email</dt>
              <dd>{user.email}</dd>

              <dt className="text-muted-foreground">Role</dt>
              <dd>
                <Badge
                  variant={user.role === "admin" ? "default" : "secondary"}
                  className="capitalize"
                >
                  {user.role}
                </Badge>
              </dd>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Change password</CardTitle>
              <CardDescription>At least 8 characters.</CardDescription>
            </div>
          </CardHeader>

          <CardContent>
            <form
              onSubmit={form.handleSubmit((values) => m.mutate(values))}
              noValidate
              className="grid max-w-sm gap-4"
            >
              <FormError message={m.error ? errorMessage(m.error) : null} />

              <Field
                label="Current password"
                htmlFor="cp-current"
                error={e.current_password?.message}
              >
                <Input
                  id="cp-current"
                  type="password"
                  autoComplete="current-password"
                  {...form.register("current_password")}
                />
              </Field>

              <Field label="New password" htmlFor="cp-new" error={e.new_password?.message}>
                <Input
                  id="cp-new"
                  type="password"
                  autoComplete="new-password"
                  {...form.register("new_password")}
                />
              </Field>

              <Field label="Confirm new password" htmlFor="cp-confirm" error={e.confirm?.message}>
                <Input
                  id="cp-confirm"
                  type="password"
                  autoComplete="new-password"
                  {...form.register("confirm")}
                />
              </Field>

              <Button type="submit" className="w-fit" disabled={m.isPending}>
                {m.isPending ? "Saving…" : "Change password"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
