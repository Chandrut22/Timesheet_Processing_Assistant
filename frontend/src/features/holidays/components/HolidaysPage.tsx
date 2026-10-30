import { getRouteApi } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type JSX } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { errorMessage } from "@/utils/errors";
import type { HolidayRead } from "../types/holiday";
import { useIsAdmin } from "@/features/auth";
import { CompanySelect, useCompanyMap } from "@/features/companies";
import { CompanyChecklist } from "./CompanyChecklist";
import { CopyHolidaysDialog } from "./CopyHolidaysDialog";
import { describeBulkResult } from "../utils/bulkResult";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Field, FormError } from "@/components/forms/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import { useHolidaysList } from "@/features/holidays";
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
import { applyFieldErrors } from "@/lib/forms";
import { formatDayLabel } from "@/utils/format";
import {
  holidayBulkStatus,
  useCreateHolidays,
  useDeleteHoliday,
  useRefreshHolidays,
} from "../hooks/useHolidayMutations";
import type { HolidaysSearch } from "../utils/holidaysSearch";

const routeApi = getRouteApi("/_app/holidays");

const THIS_YEAR = new Date().getFullYear();

const schema = z.object({
  holiday_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Pick a date"),
  name: z.string().trim().min(1, "Enter a name").max(150),
  company_ids: z.array(z.string()).min(1, "Choose at least one company"),
});
type Values = z.infer<typeof schema>;

export function HolidaysPage(): JSX.Element {
  const search = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const isAdmin = useIsAdmin();
  const companies = useCompanyMap();
  const refreshHolidays = useRefreshHolidays();
  const [deleting, setDeleting] = useState<HolidayRead | null>(null);
  const year = search.year ?? THIS_YEAR;
  const params = {
    year,
    company_id: search.company_id,
    is_active: search.active === undefined ? undefined : search.active === "active",
  };
  const list = useHolidaysList(params);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      holiday_date: "",
      name: "",
      company_ids: search.company_id ? [search.company_id] : [],
    },
  });
  // One date for every chosen company, in one request (a company that already has a
  // holiday that day is skipped and named in the message).
  const create = useCreateHolidays({
    onSuccess: (result) => {
      const message = describeBulkResult(result, (id) => companies.get(id)?.name ?? "A company");
      if (result.created > 0) toast.success(message);
      else toast.warning(message);
      form.reset({ holiday_date: "", name: "", company_ids: form.getValues("company_ids") });
    },
    onError: (err) => applyFieldErrors(err, form.setError, ["holiday_date", "name", "company_ids"]),
  });
  const remove = useDeleteHoliday({
    onSuccess: () => {
      setDeleting(null);
      toast.success("Holiday removed.");
    },
  });

  const years = Array.from({ length: 6 }, (_, i) => THIS_YEAR - 2 + i);
  const rows = useMemo(
    () =>
      [...(list.data ?? [])].sort(
        (a, b) =>
          a.holiday_date.localeCompare(b.holiday_date) ||
          (companies.get(a.company_id)?.name ?? "").localeCompare(
            companies.get(b.company_id)?.name ?? "",
          ),
      ),
    [list.data, companies],
  );
  const bulkRows = useMemo(
    () =>
      rows.map((h) => ({
        id: h.id,
        label: `${h.name} (${formatDayLabel(h.holiday_date)}, ${companies.get(h.company_id)?.name ?? "a company"})`,
        isActive: h.is_active,
      })),
    [rows, companies],
  );
  const selection = useRowSelection(bulkRows, JSON.stringify(params));

  return (
    <>
      <PageHeader
        title="Holidays"
        description="Each holiday belongs to one company. Hours worked on it are paid at that company's holiday rate, and the timesheet goes to a reviewer."
        actions={
          isAdmin ? (
            <div className="flex flex-wrap gap-2">
              <CopyHolidaysDialog years={years} defaultYear={year} />
              <ImportButton resource="holidays" onImported={refreshHolidays} />
            </div>
          ) : null
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex flex-wrap items-end gap-3">
              <div className="grid w-28 gap-1.5">
                <Label htmlFor="h-year">Year</Label>
                <NativeSelect
                  id="h-year"
                  value={String(year)}
                  onChange={(e) =>
                    void navigate({
                      search: (p) => ({ ...p, year: Number(e.target.value) }),
                      replace: true,
                    })
                  }
                >
                  {years.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid w-56 gap-1.5">
                <Label htmlFor="h-company">Company</Label>
                <CompanySelect
                  id="h-company"
                  value={search.company_id ?? ""}
                  onChange={(id) =>
                    void navigate({
                      search: (p) => ({ ...p, company_id: id || undefined }),
                      replace: true,
                    })
                  }
                />
              </div>
              <div className="grid w-32 gap-1.5">
                <Label htmlFor="h-active">Show</Label>
                <NativeSelect
                  id="h-active"
                  value={search.active ?? ""}
                  onChange={(e) =>
                    void navigate({
                      search: (p) => ({
                        ...p,
                        active: (e.target.value || undefined) as HolidaysSearch["active"],
                      }),
                      replace: true,
                    })
                  }
                >
                  <option value="">All</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </NativeSelect>
              </div>
            </div>
          </CardHeader>
          {list.isPending ? (
            <TableSkeleton rows={6} cols={isAdmin ? 6 : 4} />
          ) : list.isError ? (
            <CardContent>
              <ErrorState error={list.error} onRetry={() => void list.refetch()} />
            </CardContent>
          ) : rows.length === 0 ? (
            <CardContent>
              <EmptyState
                title={`No holidays in ${year}`}
                hint={
                  isAdmin
                    ? "Add one, import a file, or copy another company's holidays."
                    : undefined
                }
              />
            </CardContent>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {isAdmin ? (
                    <TableHead className="w-10">
                      <SelectAllCheckbox selection={selection} />
                    </TableHead>
                  ) : null}
                  <TableHead>Date</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Status</TableHead>
                  {isAdmin ? <TableHead className="w-10" /> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((h, i) => (
                  <TableRow
                    key={h.id}
                    data-state={selection.selected.has(h.id) ? "selected" : undefined}
                  >
                    {isAdmin ? (
                      <TableCell>
                        <RowCheckbox row={bulkRows[i]} selection={selection} />
                      </TableCell>
                    ) : null}
                    <TableCell className="tabular">{formatDayLabel(h.holiday_date)}</TableCell>
                    <TableCell className="font-medium">{h.name}</TableCell>
                    <TableCell>{companies.get(h.company_id)?.name ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={h.is_active ? "success" : "muted"}>
                        {h.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    {isAdmin ? (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Delete ${h.name}`}
                          onClick={() => setDeleting(h)}
                        >
                          <Trash2 />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {isAdmin ? (
          <Card className="h-fit">
            <CardHeader>
              <CardTitle>Add a holiday</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={form.handleSubmit((v) =>
                  create.mutate({
                    holiday_date: v.holiday_date,
                    name: v.name.trim(),
                    company_ids: v.company_ids,
                  }),
                )}
                noValidate
                className="grid gap-4"
              >
                <FormError message={create.error ? errorMessage(create.error) : null} />
                <Field
                  label="Date"
                  htmlFor="h-date"
                  error={form.formState.errors.holiday_date?.message}
                >
                  <Input id="h-date" type="date" {...form.register("holiday_date")} />
                </Field>
                <Field label="Name" htmlFor="h-name" error={form.formState.errors.name?.message}>
                  <Input id="h-name" placeholder="Diwali" {...form.register("name")} />
                </Field>
                <Controller
                  control={form.control}
                  name="company_ids"
                  render={({ field, fieldState }) => (
                    <CompanyChecklist
                      id="h-companies"
                      value={field.value}
                      onChange={field.onChange}
                      error={fieldState.error?.message}
                    />
                  )}
                />
                <Button type="submit" disabled={create.isPending}>
                  <Plus /> {create.isPending ? "Adding…" : "Add holiday"}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : null}
      </div>

      {isAdmin ? (
        <BulkStatusBar
          selection={selection}
          noun={{ one: "holiday", many: "holidays" }}
          api={holidayBulkStatus}
          warnings={{
            deactivate:
              "They stay in the list but are no longer paid at the holiday rate. Timesheets already priced keep their pay until they are recalculated.",
            activate:
              "Hours on these days are paid at the holiday rate again, for timesheets calculated from now on.",
            delete:
              "They are removed for good. Timesheets already priced keep their pay until they are recalculated. To keep them on record, deactivate them instead.",
          }}
        />
      ) : null}

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "holiday"}?`}
        description="Timesheets calculated from now on won't treat this day as a holiday. Earlier ones keep their pay until recalculated."
        confirmLabel="Delete"
        destructive
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </>
  );
}

/** The page's search params, checked when the URL changes. */
