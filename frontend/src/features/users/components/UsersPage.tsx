import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { errorMessage } from "@/services/apiErrors";
import type { RoleName } from "@/types/api";
import type { UserRead } from "../types/user";
import { useUser } from "@/features/auth";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Field, FormError } from "@/components/forms/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { Pagination } from "@/components/common/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BulkStatusBar, RowCheckbox, SelectAllCheckbox } from "@/components/common/BulkStatusBar";
import { useRowSelection } from "@/hooks/useRowSelection";
import { ImportButton } from "@/features/import";
import { DebouncedInput } from "@/components/forms/DebouncedInput";
import { applyFieldErrors } from "@/lib/forms";
import { formatDate, formatRelative } from "@/utils/format";
import { userService } from "../services/userService";
import { userKeys } from "../queries/userQueries";

export function UsersPage() {
  const me = useUser();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"" | RoleName>("");
  const [active, setActive] = useState<"" | "true" | "false">("true");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<UserRead | null>(null);
  const [toggling, setToggling] = useState<UserRead | null>(null);

  const params = {
    q: q || undefined,
    role: role || undefined,
    is_active: active === "" ? undefined : active === "true",
    page,
    size: 25,
  };
  const list = useQuery({
    queryKey: userKeys.list(params),
    queryFn: ({ signal }) => userService.listUsers(params, signal),
    placeholderData: keepPreviousData,
  });
  const bulkRows = useMemo(
    () =>
      (list.data?.items ?? []).map((u) => ({
        id: u.id,
        label: `${u.name} (${u.email})`,
        isActive: u.is_active,
        disabled: u.id === me.id,
        disabledReason: "You can't change your own status",
      })),
    [list.data, me.id],
  );
  const selection = useRowSelection(bulkRows, JSON.stringify(params));

  // The backend refuses changing your own role or demoting the last admin; its message is shown in a toast.
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { role?: RoleName; is_active?: boolean } }) =>
      userService.updateUser(id, body),
    onSuccess: (u) => {
      toast.success(`${u.name} updated.`);
      setToggling(null);
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });

  return (
    <>
      <PageHeader
        title="Users"
        description="People who can sign in. Reviewers check timesheets; admins also export payroll and manage setup."
        actions={
          <>
            <ImportButton
              resource="users"
              onImported={() => void queryClient.invalidateQueries({ queryKey: userKeys.all })}
            />
            <Button onClick={() => setCreating(true)}>
              <Plus /> New user
            </Button>
          </>
        }
      />
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-4">
        <div className="grid gap-1.5">
          <Label htmlFor="u-q">Search</Label>
          <DebouncedInput
            id="u-q"
            type="search"
            placeholder="Name or email"
            value={q}
            onCommit={(v) => {
              setQ(v.trim());
              setPage(1);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="u-role">Role</Label>
          <NativeSelect
            id="u-role"
            value={role}
            onChange={(e) => {
              setRole(e.target.value as typeof role);
              setPage(1);
            }}
          >
            <option value="">All roles</option>
            <option value="admin">Admin</option>
            <option value="reviewer">Reviewer</option>
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="u-active">Show</Label>
          <NativeSelect
            id="u-active"
            value={active}
            onChange={(e) => {
              setActive(e.target.value as typeof active);
              setPage(1);
            }}
          >
            <option value="true">Active</option>
            <option value="false">Deactivated</option>
            <option value="">All</option>
          </NativeSelect>
        </div>
      </Card>

      <Card>
        {list.isPending ? (
          <TableSkeleton rows={5} cols={8} />
        ) : list.isError ? (
          <div className="p-4">
            <ErrorState error={list.error} onRetry={() => void list.refetch()} />
          </div>
        ) : list.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No users found" />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <SelectAllCheckbox selection={selection} />
                  </TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last sign-in</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.items.map((u, i) => {
                  const isMe = u.id === me.id;
                  return (
                    <TableRow
                      key={u.id}
                      data-state={selection.selected.has(u.id) ? "selected" : undefined}
                    >
                      <TableCell>
                        <RowCheckbox row={bulkRows[i]} selection={selection} />
                      </TableCell>
                      <TableCell className="font-medium">
                        {u.name} {isMe ? <Badge variant="secondary">You</Badge> : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{u.email}</TableCell>
                      <TableCell>
                        <NativeSelect
                          aria-label={`Role of ${u.name}`}
                          className="h-8 w-32"
                          value={u.role}
                          disabled={isMe || update.isPending}
                          title={isMe ? "You can't change your own role" : undefined}
                          onChange={(e) =>
                            update.mutate({ id: u.id, body: { role: e.target.value as RoleName } })
                          }
                        >
                          <option value="admin">Admin</option>
                          <option value="reviewer">Reviewer</option>
                        </NativeSelect>
                      </TableCell>
                      <TableCell>
                        <Badge variant={u.is_active ? "success" : "muted"}>
                          {u.is_active ? "Active" : "Deactivated"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {u.last_login_at ? formatRelative(u.last_login_at) : "Never"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(u.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="sm" onClick={() => setResetting(u)}>
                            <KeyRound /> Password
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={isMe}
                            onClick={() => setToggling(u)}
                          >
                            {u.is_active ? "Deactivate" : "Reactivate"}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <Pagination page={page} size={25} total={list.data.total} onPage={setPage} />
          </>
        )}
      </Card>

      <BulkStatusBar
        selection={selection}
        noun={{ one: "user", many: "users" }}
        setStatus={userService.bulkUserStatus}
        invalidate={[userKeys.all]}
        warnings={{
          deactivate:
            "They can't sign in any more and are signed out within minutes. Their past work is kept. The last active admin always stays.",
          activate: "They'll be able to sign in again with their current password.",
        }}
      />
      <CreateUserDialog open={creating} onOpenChange={setCreating} />
      {resetting ? (
        <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />
      ) : null}
      <ConfirmDialog
        open={!!toggling}
        onOpenChange={(o) => !o && setToggling(null)}
        title={
          toggling?.is_active
            ? `Deactivate ${toggling?.name}?`
            : `Reactivate ${toggling?.name ?? ""}?`
        }
        description={
          toggling?.is_active
            ? "They won't be able to sign in. Their past work is kept."
            : "They'll be able to sign in again."
        }
        confirmLabel={toggling?.is_active ? "Deactivate" : "Reactivate"}
        destructive={!!toggling?.is_active}
        pending={update.isPending}
        onConfirm={() =>
          toggling && update.mutate({ id: toggling.id, body: { is_active: !toggling.is_active } })
        }
      />
    </>
  );
}

const createSchema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(150),
  email: z.email("Enter a valid email address"),
  password: z.string().min(8, "At least 8 characters").max(128),
  role: z.enum(["admin", "reviewer"]),
});
type CreateValues = z.infer<typeof createSchema>;

function CreateUserDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { name: "", email: "", password: "", role: "reviewer" },
  });
  const m = useMutation({
    mutationFn: (v: CreateValues) =>
      userService.createUser({ ...v, name: v.name.trim(), email: v.email.trim() }),
    meta: { silentError: true },
    onSuccess: (u) => {
      toast.success(`${u.name} can now sign in.`);
      form.reset();
      onOpenChange(false);
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
    onError: (err) => applyFieldErrors(err, form.setError, ["name", "email", "password", "role"]),
  });
  const e = form.formState.errors;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) m.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New user</DialogTitle>
            <DialogDescription>
              Share the password with them; they can change it under Account.
            </DialogDescription>
          </DialogHeader>
          <FormError message={m.error ? errorMessage(m.error) : null} />
          <Field label="Name" htmlFor="nu-name" error={e.name?.message}>
            <Input id="nu-name" {...form.register("name")} />
          </Field>
          <Field label="Email" htmlFor="nu-email" error={e.email?.message}>
            <Input id="nu-email" type="email" autoComplete="off" {...form.register("email")} />
          </Field>
          <Field
            label="Password"
            htmlFor="nu-password"
            error={e.password?.message}
            hint="At least 8 characters"
          >
            <Input
              id="nu-password"
              type="password"
              autoComplete="new-password"
              {...form.register("password")}
            />
          </Field>
          <Field label="Role" htmlFor="nu-role" error={e.role?.message}>
            <NativeSelect id="nu-role" {...form.register("role")}>
              <option value="reviewer">Reviewer</option>
              <option value="admin">Admin</option>
            </NativeSelect>
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={m.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={m.isPending}>
              {m.isPending ? "Creating…" : "Create user"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const resetSchema = z
  .object({
    new_password: z.string().min(8, "At least 8 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "The passwords don't match",
  });
type ResetValues = z.infer<typeof resetSchema>;

function ResetPasswordDialog({ user, onClose }: { user: UserRead; onClose: () => void }) {
  const form = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { new_password: "", confirm: "" },
  });
  const m = useMutation({
    mutationFn: (v: ResetValues) => userService.setUserPassword(user.id, v.new_password),
    meta: { silentError: true },
    onSuccess: () => {
      toast.success(`Password changed for ${user.name}.`);
      onClose();
    },
    onError: (err) => applyFieldErrors(err, form.setError, ["new_password"]),
  });
  const e = form.formState.errors;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => m.mutate(v))} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Set a new password for {user.name}</DialogTitle>
            <DialogDescription>
              Tell them the new password; their current one stops working.
            </DialogDescription>
          </DialogHeader>
          <FormError message={m.error ? errorMessage(m.error) : null} />
          <Field label="New password" htmlFor="rp-new" error={e.new_password?.message}>
            <Input
              id="rp-new"
              type="password"
              autoComplete="new-password"
              {...form.register("new_password")}
            />
          </Field>
          <Field label="Confirm" htmlFor="rp-confirm" error={e.confirm?.message}>
            <Input
              id="rp-confirm"
              type="password"
              autoComplete="new-password"
              {...form.register("confirm")}
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={onClose} disabled={m.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={m.isPending}>
              {m.isPending ? "Saving…" : "Set password"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
