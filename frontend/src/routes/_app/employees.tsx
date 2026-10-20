import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import type { EmployeeRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { useIsAdmin } from "@/auth/useSession";
import { CompanySelect } from "@/components/CompanySelect";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmployeeForm, type EmployeeFormValues } from "@/features/employees/EmployeeForm";
import { toEmployeeCreate, toEmployeeUpdate } from "@/features/employees/employee-utils";
import { DebouncedInput } from "@/features/review/DebouncedInput";
import { formatDate } from "@/lib/format";
import { useCompanyMap } from "@/lib/lookups";

type EmployeesSearch = {
  company_id?: string;
  q?: string;
  active?: "all" | "inactive";
  page?: number;
};

export const Route = createFileRoute("/_app/employees")({
  validateSearch: (s: Record<string, unknown>): EmployeesSearch => ({
    company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
    q: typeof s.q === "string" && s.q ? s.q : undefined,
    active: s.active === "all" || s.active === "inactive" ? s.active : undefined,
    page: Number.isInteger(Number(s.page)) && Number(s.page) > 1 ? Number(s.page) : undefined,
  }),
  component: EmployeesPage,
});

function EmployeesPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  const companies = useCompanyMap();
  const [editing, setEditing] = useState<EmployeeRead | "new" | null>(null);

  const params = {
    company_id: search.company_id,
    q: search.q,
    is_active: search.active === "all" ? undefined : search.active !== "inactive",
    page: search.page ?? 1,
    size: 25,
  };
  const list = useQuery({
    queryKey: qk.employees.list(params),
    queryFn: () => coreApi.listEmployees(params),
    placeholderData: keepPreviousData,
  });

  const update = (patch: Partial<EmployeesSearch>) =>
    void navigate({
      search: (prev) => ({ ...prev, ...patch, page: "page" in patch ? patch.page : undefined }),
      replace: true,
    });

  const save = useMutation({
    mutationFn: (v: EmployeeFormValues) =>
      editing && editing !== "new"
        ? coreApi.updateEmployee(editing.id, toEmployeeUpdate(v))
        : coreApi.createEmployee(toEmployeeCreate(v)),
    meta: { silentError: true },
    onSuccess: (e) => {
      toast.success(editing === "new" ? `${e.full_name} added.` : "Saved.");
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: qk.employees.all });
    },
  });

  return (
    <>
      <PageHeader
        title="Employees"
        description="People placed at client companies. Timesheets are matched to them."
        actions={
          isAdmin ? (
            <Button onClick={() => setEditing("new")}>
              <Plus /> New employee
            </Button>
          ) : null
        }
      />
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-4">
        <div className="grid gap-1.5">
          <Label htmlFor="em-company">Company</Label>
          <CompanySelect
            id="em-company"
            value={search.company_id ?? ""}
            onChange={(company_id) => update({ company_id: company_id || undefined })}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="em-q">Search</Label>
          <DebouncedInput
            id="em-q"
            type="search"
            placeholder="Name or code"
            value={search.q ?? ""}
            onCommit={(q) => update({ q: q.trim() || undefined })}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="em-active">Show</Label>
          <NativeSelect
            id="em-active"
            value={search.active ?? "active"}
            onChange={(e) =>
              update({
                active:
                  e.target.value === "active" ? undefined : (e.target.value as "all" | "inactive"),
              })
            }
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="all">All</option>
          </NativeSelect>
        </div>
      </Card>

      <Card>
        {list.isPending ? (
          <TableSkeleton rows={6} cols={6} />
        ) : list.isError ? (
          <div className="p-4">
            <ErrorState error={list.error} onRetry={() => void list.refetch()} />
          </div>
        ) : list.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No employees found" />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Assignment</TableHead>
                  <TableHead>Status</TableHead>
                  {isAdmin ? <TableHead className="w-10" /> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="tabular">{e.employee_code}</TableCell>
                    <TableCell>
                      <span className="font-medium">{e.full_name}</span>
                      {e.aliases.length ? (
                        <span className="block max-w-56 truncate text-xs text-muted-foreground">
                          {e.aliases.join(", ")}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>{companies.get(e.company_id)?.name ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{e.email ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {e.assignment_start ? formatDate(e.assignment_start) : "—"} –{" "}
                      {e.assignment_end ? formatDate(e.assignment_end) : "ongoing"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={e.is_active ? "success" : "muted"}>
                        {e.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    {isAdmin ? (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Edit ${e.full_name}`}
                          onClick={() => setEditing(e)}
                        >
                          <Pencil />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={params.page}
              size={25}
              total={list.data.total}
              onPage={(page) => update({ page })}
            />
          </>
        )}
      </Card>

      <Dialog
        open={editing !== null}
        onOpenChange={(o) => {
          if (!o) {
            setEditing(null);
            save.reset();
          }
        }}
      >
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "New employee" : "Edit employee"}</DialogTitle>
          </DialogHeader>
          {editing !== null ? (
            <EmployeeForm
              key={editing === "new" ? "new" : editing.id}
              employee={editing === "new" ? undefined : editing}
              defaultCompanyId={search.company_id}
              onSubmit={(v) => save.mutateAsync(v)}
              onCancel={() => setEditing(null)}
              serverError={save.error ? errorMessage(save.error) : null}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
