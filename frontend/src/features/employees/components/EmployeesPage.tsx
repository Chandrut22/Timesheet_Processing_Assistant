import { getRouteApi } from "@tanstack/react-router";
import { useEmployeesList } from "@/features/employees";
import { Pencil, Plus } from "lucide-react";
import { useMemo, useState, type JSX } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/utils/errors";
import type { EmployeeRead } from "../types/employee";
import { useIsAdmin } from "@/features/auth";
import { CompanySelect, useCompanyMap } from "@/features/companies";
import { PageHeader } from "@/components/common/PageHeader";
import { Pagination } from "@/components/common/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
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
import { BulkStatusBar, RowCheckbox, SelectAllCheckbox } from "@/components/common/BulkStatusBar";
import { useRowSelection } from "@/hooks/useRowSelection";
import { EmployeeForm, type EmployeeFormValues } from "./EmployeeForm";
import { toEmployeeCreate, toEmployeeUpdate } from "../utils/employeeUtils";
import { ImportButton } from "@/features/import";
import { DebouncedInput } from "@/components/forms/DebouncedInput";
import { formatDate } from "@/utils/format";
import {
  employeeBulkStatus,
  useRefreshEmployees,
  useSaveEmployee,
} from "../hooks/useEmployeeMutations";
import type { EmployeesSearch } from "../utils/employeesSearch";

const routeApi = getRouteApi("/_app/employees");

export function EmployeesPage(): JSX.Element {
  const search = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const isAdmin = useIsAdmin();
  const companies = useCompanyMap();
  const [editing, setEditing] = useState<EmployeeRead | "new" | null>(null);

  const params = {
    company_id: search.company_id,
    q: search.q,
    is_active: search.active === "all" ? undefined : search.active !== "inactive",
    page: search.page ?? 1,
    size: 25,
  };
  const list = useEmployeesList(params);
  const bulkRows = useMemo(
    () =>
      (list.data?.items ?? []).map((e) => ({
        id: e.id,
        label: `${e.full_name} (${e.employee_code})`,
        isActive: e.is_active,
      })),
    [list.data],
  );
  const selection = useRowSelection(bulkRows, JSON.stringify(params));

  const update = (patch: Partial<EmployeesSearch>): void =>
    void navigate({
      search: (prev) => ({ ...prev, ...patch, page: "page" in patch ? patch.page : undefined }),
      replace: true,
    });

  const refreshEmployees = useRefreshEmployees();
  const save = useSaveEmployee({
    onSuccess: (e, v) => {
      toast.success(v.id === null ? `${e.full_name} added.` : "Saved.");
      setEditing(null);
    },
  });

  return (
    <>
      <PageHeader
        title="Employees"
        description="People placed at client companies. Timesheets are matched to them."
        actions={
          isAdmin ? (
            <>
              <ImportButton resource="employees" onImported={refreshEmployees} />
              <Button onClick={() => setEditing("new")}>
                <Plus /> New employee
              </Button>
            </>
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
          <TableSkeleton rows={6} cols={isAdmin ? 8 : 6} />
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
                  {isAdmin ? (
                    <TableHead className="w-10">
                      <SelectAllCheckbox selection={selection} />
                    </TableHead>
                  ) : null}
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
                {list.data.items.map((e, i) => (
                  <TableRow
                    key={e.id}
                    data-state={selection.selected.has(e.id) ? "selected" : undefined}
                  >
                    {isAdmin ? (
                      <TableCell>
                        <RowCheckbox row={bulkRows[i]} selection={selection} />
                      </TableCell>
                    ) : null}
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

      {isAdmin ? (
        <BulkStatusBar
          selection={selection}
          noun={{ one: "employee", many: "employees" }}
          api={employeeBulkStatus}
          warnings={{
            deactivate:
              "Timesheets that arrive for them are no longer matched to them. Their past timesheets are kept.",
            activate: "Employees of an inactive company stay inactive: activate the company first.",
          }}
        />
      ) : null}

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
              onSubmit={(v: EmployeeFormValues) =>
                save.mutateAsync(
                  editing && editing !== "new"
                    ? { id: editing.id, body: toEmployeeUpdate(v) }
                    : { id: null, body: toEmployeeCreate(v) },
                )
              }
              onCancel={() => setEditing(null)}
              serverError={save.error ? errorMessage(save.error) : null}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** The page's search params, checked when the URL changes. */
