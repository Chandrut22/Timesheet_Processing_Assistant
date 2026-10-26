import { Link, useNavigate } from "@tanstack/react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/services/apiErrors";
import { useIsAdmin } from "@/features/auth";
import { Money } from "@/components/common/Money";
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { CompanyForm, type CompanyFormValues } from "./CompanyForm";
import { toCompanyBody } from "../utils/companyUtils";
import { ImportButton } from "@/features/import";
import { DebouncedInput } from "@/components/forms/DebouncedInput";
import { WEEKDAYS } from "@/utils/format";
import { companyService } from "../services/companyService";
import { companyKeys } from "../queries/companyQueries";
import { employeeKeys } from "@/features/employees";

export function CompaniesPage() {
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [q, setQ] = useState("");
  const [active, setActive] = useState<"" | "true" | "false">("true");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  const params = {
    q: q || undefined,
    is_active: active === "" ? undefined : active === "true",
    page,
    size: 25,
  };

  const list = useQuery({
    queryKey: companyKeys.list(params),
    queryFn: ({ signal }) => companyService.listCompanies(params, signal),
    placeholderData: keepPreviousData,
  });
  const bulkRows = useMemo(
    () => (list.data?.items ?? []).map((c) => ({ id: c.id, label: c.name, isActive: c.is_active })),
    [list.data],
  );
  const selection = useRowSelection(bulkRows, JSON.stringify(params));

  const create = useMutation({
    mutationFn: (v: CompanyFormValues) => companyService.createCompany(toCompanyBody(v)),
    meta: { silentError: true },

    onSuccess: (c) => {
      toast.success(`${c.name} created. Next, add the email addresses it sends timesheets from.`);

      void queryClient.invalidateQueries({
        queryKey: companyKeys.all,
      });

      setCreating(false);

      void navigate({
        to: "/companies/$companyId",
        params: { companyId: c.id },
        search: { tab: "senders" },
      });
    },
  });

  return (
    <>
      <PageHeader
        title="Companies"
        description="Client companies, their pay rates and rules, and who may send their timesheets."
        actions={
          isAdmin ? (
            <>
              <ImportButton
                resource="companies"
                onImported={() =>
                  void queryClient.invalidateQueries({
                    queryKey: companyKeys.all,
                  })
                }
              />

              <Button onClick={() => setCreating(true)}>
                <Plus />
                New company
              </Button>
            </>
          ) : null
        }
      />

      <Card className="mb-4 flex flex-wrap items-end gap-3 p-4">
        <div className="grid w-full max-w-xs gap-1.5">
          <Label htmlFor="co-q">Search</Label>

          <DebouncedInput
            id="co-q"
            type="search"
            placeholder="Name"
            value={q}
            onCommit={(v) => {
              setQ(v.trim());
              setPage(1);
            }}
          />
        </div>

        <div className="grid w-40 gap-1.5">
          <Label htmlFor="co-active">Show</Label>

          <NativeSelect
            id="co-active"
            value={active}
            onChange={(e) => {
              setActive(e.target.value as typeof active);
              setPage(1);
            }}
          >
            <option value="true">Active</option>
            <option value="false">Inactive</option>
            <option value="">All</option>
          </NativeSelect>
        </div>
      </Card>

      <Card>
        {list.isPending ? (
          <TableSkeleton rows={6} cols={isAdmin ? 9 : 7} />
        ) : list.isError ? (
          <div className="p-4">
            <ErrorState error={list.error} onRetry={() => void list.refetch()} />
          </div>
        ) : list.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No companies found"
              hint={isAdmin ? 'Create the first one with "New company".' : undefined}
            />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  {isAdmin && (
                    <TableHead className="w-10">
                      <SelectAllCheckbox selection={selection} />
                    </TableHead>
                  )}
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Regular</TableHead>
                  <TableHead className="text-right">Overtime</TableHead>
                  <TableHead className="text-right">Holiday</TableHead>
                  <TableHead>Overtime after</TableHead>
                  <TableHead>Week starts</TableHead>
                  <TableHead>Status</TableHead>

                  {isAdmin && <TableHead className="text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>

              <TableBody>
                {list.data.items.map((c, i) => (
                  <TableRow
                    key={c.id}
                    data-state={selection.selected.has(c.id) ? "selected" : undefined}
                  >
                    {isAdmin && (
                      <TableCell>
                        <RowCheckbox row={bulkRows[i]} selection={selection} />
                      </TableCell>
                    )}
                    <TableCell>
                      <Link
                        to="/companies/$companyId"
                        params={{ companyId: c.id }}
                        className="font-medium hover:underline"
                      >
                        {c.name}
                      </Link>

                      {c.aliases.length > 0 && (
                        <span className="block max-w-64 truncate text-xs text-muted-foreground">
                          {c.aliases.join(", ")}
                        </span>
                      )}
                    </TableCell>

                    <TableCell className="text-right">
                      <Money amount={c.hourly_rate} currency={c.currency} />
                    </TableCell>

                    <TableCell className="text-right">
                      <Money amount={c.overtime_rate} currency={c.currency} />
                    </TableCell>

                    <TableCell className="text-right">
                      <Money amount={c.holiday_rate} currency={c.currency} />
                    </TableCell>

                    <TableCell className="tabular">
                      {c.daily_ot_after} h/day · {c.weekly_ot_after} h/week
                    </TableCell>

                    <TableCell>{WEEKDAYS[c.week_start]}</TableCell>

                    <TableCell>
                      <Badge variant={c.is_active ? "success" : "muted"}>
                        {c.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>

                    {isAdmin && (
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Edit ${c.name}`}
                          onClick={() =>
                            void navigate({
                              to: "/companies/$companyId",
                              params: { companyId: c.id },
                            })
                          }
                        >
                          <Pencil />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <Pagination page={page} size={25} total={list.data.total} onPage={setPage} />
          </>
        )}
      </Card>

      {isAdmin ? (
        <BulkStatusBar
          selection={selection}
          noun={{ one: "company", many: "companies" }}
          setStatus={companyService.bulkCompanyStatus}
          invalidate={[companyKeys.all, employeeKeys.all]}
          warnings={{
            deactivate:
              "All their employees are deactivated too. Timesheets from these companies are no longer matched.",
            activate:
              "Their employees stay inactive. Activate the ones you need on the Employees page.",
          }}
        />
      ) : null}

      <Dialog
        open={creating}
        onOpenChange={(open) => {
          if (!open) {
            create.reset();
          }

          setCreating(open);
        }}
      >
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>New company</DialogTitle>

            <DialogDescription>
              Pay rates are required. You can change them later.
            </DialogDescription>
          </DialogHeader>

          <CompanyForm
            submitLabel="Create company"
            onSubmit={(v) => create.mutateAsync(v)}
            onCancel={() => setCreating(false)}
            serverError={create.error ? errorMessage(create.error) : null}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
