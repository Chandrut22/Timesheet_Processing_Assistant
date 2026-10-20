import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import type { HolidayRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { useIsAdmin } from "@/auth/useSession";
import { CompanySelect } from "@/components/CompanySelect";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Field, FormError } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { applyFieldErrors } from "@/lib/forms";
import { formatDayLabel } from "@/lib/format";
import { useCompanyMap } from "@/lib/lookups";

type HolidaysSearch = { year?: number; company_id?: string };
const THIS_YEAR = new Date().getFullYear();

export const Route = createFileRoute("/_app/holidays")({
  validateSearch: (s: Record<string, unknown>): HolidaysSearch => {
    const y = Number(s.year);
    return {
      year: Number.isInteger(y) && y >= 2000 && y <= 2100 ? y : undefined,
      company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
    };
  },
  component: HolidaysPage,
});

const schema = z.object({
  holiday_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Pick a date"),
  name: z.string().trim().min(1, "Enter a name").max(150),
  company_id: z.string(),
});
type Values = z.infer<typeof schema>;

function HolidaysPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const isAdmin = useIsAdmin();
  const companies = useCompanyMap();
  const queryClient = useQueryClient();
  const [deleting, setDeleting] = useState<HolidayRead | null>(null);
  const year = search.year ?? THIS_YEAR;
  const params = { year, company_id: search.company_id };
  const list = useQuery({ queryKey: qk.holidays.list(params), queryFn: () => coreApi.listHolidays(params) });

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { holiday_date: "", name: "", company_id: search.company_id ?? "" },
  });
  const create = useMutation({
    mutationFn: (v: Values) =>
      coreApi.createHoliday({ holiday_date: v.holiday_date, name: v.name.trim(), company_id: v.company_id || null }),
    meta: { silentError: true },
    onSuccess: (h) => {
      toast.success(`${h.name} added.`);
      form.reset({ holiday_date: "", name: "", company_id: form.getValues("company_id") });
      void queryClient.invalidateQueries({ queryKey: qk.holidays.all });
    },
    onError: (err) => applyFieldErrors(err, form.setError, ["holiday_date", "name", "company_id"]),
  });
  const remove = useMutation({
    mutationFn: (h: HolidayRead) => coreApi.deleteHoliday(h.id),
    onSuccess: () => {
      setDeleting(null);
      toast.success("Holiday removed.");
      void queryClient.invalidateQueries({ queryKey: qk.holidays.all });
    },
  });

  const years = Array.from({ length: 6 }, (_, i) => THIS_YEAR - 2 + i);
  const rows = [...(list.data ?? [])].sort((a, b) => a.holiday_date.localeCompare(b.holiday_date));

  return (
    <>
      <PageHeader
        title="Holidays"
        description="Hours worked on these days are paid at the holiday rate. A holiday with no company applies to all of them."
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
                  onChange={(e) => void navigate({ search: (p) => ({ ...p, year: Number(e.target.value) }), replace: true })}
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
                  onChange={(id) => void navigate({ search: (p) => ({ ...p, company_id: id || undefined }), replace: true })}
                />
              </div>
            </div>
          </CardHeader>
          {list.isPending ? (
            <TableSkeleton rows={6} cols={3} />
          ) : list.isError ? (
            <CardContent><ErrorState error={list.error} onRetry={() => void list.refetch()} /></CardContent>
          ) : rows.length === 0 ? (
            <CardContent><EmptyState title={`No holidays in ${year}`} /></CardContent>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Applies to</TableHead>
                  {isAdmin ? <TableHead className="w-10" /> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell className="tabular">{formatDayLabel(h.holiday_date)}</TableCell>
                    <TableCell className="font-medium">{h.name}</TableCell>
                    <TableCell>
                      {h.company_id ? (
                        companies.get(h.company_id)?.name ?? "One company"
                      ) : (
                        <Badge variant="secondary">All companies</Badge>
                      )}
                    </TableCell>
                    {isAdmin ? (
                      <TableCell>
                        <Button variant="ghost" size="icon-sm" aria-label={`Delete ${h.name}`} onClick={() => setDeleting(h)}>
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
              <form onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate className="grid gap-4">
                <FormError message={create.error ? errorMessage(create.error) : null} />
                <Field label="Date" htmlFor="h-date" error={form.formState.errors.holiday_date?.message}>
                  <Input id="h-date" type="date" {...form.register("holiday_date")} />
                </Field>
                <Field label="Name" htmlFor="h-name" error={form.formState.errors.name?.message}>
                  <Input id="h-name" placeholder="Diwali" {...form.register("name")} />
                </Field>
                <Field label="Applies to" htmlFor="h-scope">
                  <Controller
                    control={form.control}
                    name="company_id"
                    render={({ field }) => (
                      <CompanySelect id="h-scope" value={field.value} onChange={field.onChange} allLabel="All companies" activeOnly />
                    )}
                  />
                </Field>
                <Button type="submit" disabled={create.isPending}>
                  <Plus /> {create.isPending ? "Adding…" : "Add holiday"}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : null}
      </div>

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
