import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { errorMessage } from "@/services/apiErrors";
import { useUser, authService } from "@/features/auth";
import { Field, FormError } from "@/components/forms/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/lib/forms";

const schema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z.string().min(8, "At least 8 characters").max(128, "At most 128 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "The passwords don't match",
  })
  .refine((v) => v.new_password !== v.current_password, {
    path: ["new_password"],
    message: "Choose a password different from the current one",
  });
type Values = z.infer<typeof schema>;

export function AccountPage() {
  const user = useUser();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  });
  const m = useMutation({
    mutationFn: (v: Values) => authService.changePassword(v.current_password, v.new_password),
    meta: { silentError: true },
    onSuccess: () => {
      toast.success("Password changed.");
      form.reset();
    },
    onError: (err) => applyFieldErrors(err, form.setError, ["current_password", "new_password"]),
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
              onSubmit={form.handleSubmit((v) => m.mutate(v))}
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
