import { getRouteApi, Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, FileSpreadsheet } from "lucide-react";
import { useState, type JSX } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/utils/errors";
import { type CompanyRead, CompanySelect, useCompanyMap } from "@/features/companies";
import type { ExportBatchRead, ExportPreview } from "../types/export";
import { FormError } from "@/components/forms/Field";
import { Money } from "@/components/common/Money";
import { PageHeader } from "@/components/common/PageHeader";
import { Pagination } from "@/components/common/Pagination";
import { Banner, EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { useExportPreview, useExportHistory } from "@/features/export";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, Label } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DownloadButtons } from "./DownloadButtons";
import {
  backendWeekday,
  formatDateTime,
  formatHours,
  formatWeek,
  latestWeekStart,
  shiftIsoDate,
  WEEKDAYS,
} from "@/utils/format";
import { useCreateExport } from "../hooks/useExportActions";
import { BackButton } from "@/components/common/BackButton";
import type { ExportSearch } from "../utils/exportSearch";

const routeApi = getRouteApi("/_app/export");

// Admins and reviewers: no role guard (the API's export routes allow both).

export function ExportPage(): JSX.Element {
  const search = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const companies = useCompanyMap();
  const company = search.company_id ? companies.get(search.company_id) : undefined;
  const week = search.week ?? (company ? latestWeekStart(company.week_start) : undefined);
  const weekOk = !!company && !!week && backendWeekday(week) === company.week_start;

  const setSearch = (patch: ExportSearch): void =>
    void navigate({ search: (prev) => ({ ...prev, ...patch }), replace: true });

  const onCompany = (id: string): void => {
    const c = companies.get(id);
    setSearch({ company_id: id || undefined, week: c ? latestWeekStart(c.week_start) : undefined });
  };

  return (
    <>
      <PageHeader
        title="Payroll export"
        back={<BackButton fallback="/" fallbackLabel="Dashboard" />}
        description="Create the weekly payroll sheet for one client company from its approved timesheets, then download it as CSV or Excel."
      />

      <Card className="mb-4">
        <CardContent className="grid gap-4 pt-5 sm:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[20rem_auto_1fr]">
          <div className="grid gap-1.5">
            <Label htmlFor="ex-company">Company</Label>
            <CompanySelect
              id="ex-company"
              value={search.company_id ?? ""}
              onChange={onCompany}
              includeAll={false}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ex-week">Week starting</Label>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                aria-label="Previous week"
                disabled={!weekOk}
                onClick={() => week && setSearch({ week: shiftIsoDate(week, -7) })}
              >
                <ChevronLeft />
              </Button>
              <Input
                id="ex-week"
                type="date"
                className="w-44"
                disabled={!company}
                value={week ?? ""}
                aria-invalid={!!company && !!week && !weekOk}
                onChange={(e) => setSearch({ week: e.target.value || undefined })}
              />
              <Button
                variant="outline"
                size="icon"
                aria-label="Next week"
                disabled={!weekOk}
                onClick={() => week && setSearch({ week: shiftIsoDate(week, 7) })}
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
          <div className="self-end pb-2 text-sm text-muted-foreground">
            {company ? (
              weekOk ? (
                <>
                  Week {formatWeek(week)} · weeks start on {WEEKDAYS[company.week_start]}
                </>
              ) : (
                <span className="text-destructive">
                  {company.name}'s weeks start on {WEEKDAYS[company.week_start]}. Pick a{" "}
                  {WEEKDAYS[company.week_start]}.
                </span>
              )
            ) : (
              "Choose a company to see its week."
            )}
          </div>
        </CardContent>
      </Card>

      {company && week && weekOk ? (
        <PreviewSection company={company} week={week} />
      ) : (
        <EmptyState title="Nothing to preview yet" hint="Choose a company and a week." />
      )}

      <History key={search.company_id ?? "all"} companyId={search.company_id} />
    </>
  );
}

function PreviewSection({ company, week }: { company: CompanyRead; week: string }): JSX.Element {
  const [allowPending, setAllowPending] = useState(false);
  const [created, setCreated] = useState<ExportBatchRead | null>(null);
  const preview = useExportPreview(company.id, week);

  const create = useCreateExport(company.id, week, {
    onSuccess: (batch) => {
      setCreated(batch);
      toast.success(`Payroll sheet created with ${batch.row_count} rows.`);
    },
  });

  if (preview.isPending)
    return (
      <Card>
        <TableSkeleton rows={5} cols={8} />
      </Card>
    );
  if (preview.isError)
    return <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />;

  const p = preview.data;
  const blocked = p.problems.length > 0;
  const canExport = !blocked && p.rows.length > 0 && !(p.pending_review > 0 && !allowPending);

  return (
    <div className="space-y-4">
      {created && created.week_start === week && created.company_id === company.id ? (
        <Banner tone="success" className="flex flex-wrap items-center justify-between gap-3">
          <span>
            Created <strong>{created.filename}</strong>: {created.row_count} rows,{" "}
            <Money amount={created.gross_amount} currency={created.currency} /> gross. Its
            timesheets are now marked exported.
          </span>
          <DownloadButtons batch={created} />
        </Banner>
      ) : null}

      {blocked ? (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          <p className="font-semibold">Export blocked: someone would be paid twice</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {p.problems.map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
          <p className="mt-2">
            Reject or fix the duplicate timesheets in the review queue, then preview again.
          </p>
        </div>
      ) : null}

      <Warnings p={p} />

      <Card>
        <CardHeader>
          <div>
            <CardTitle>
              {p.company_name} · {formatWeek(p.week_start)}
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              {p.totals.rows} rows · {formatHours(p.totals.total_hours)} h ·{" "}
              <Money amount={p.totals.gross_amount} currency={p.currency} /> gross
              {p.totals.unpriced > 0 ? ` · ${p.totals.unpriced} without a rate` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {p.pending_review > 0 ? (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={allowPending}
                  onChange={(e) => setAllowPending(e.target.checked)}
                />
                Export even though {p.pending_review} still need review
              </label>
            ) : null}
            <Button
              onClick={() => create.mutate(allowPending)}
              disabled={!canExport || create.isPending}
            >
              <FileSpreadsheet /> {create.isPending ? "Creating…" : "Create payroll sheet"}
            </Button>
          </div>
        </CardHeader>
        {create.error ? (
          <div className="px-5 pb-3">
            {/* 409s (e.g. double pay found at export time) are shown as the backend wrote them. */}
            <FormError message={errorMessage(create.error)} />
          </div>
        ) : null}
        {p.rows.length === 0 ? (
          <CardContent>
            <EmptyState
              title="No approved timesheets for this week"
              hint="Approve timesheets in the review queue first."
            />
          </CardContent>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead className="text-right">Regular</TableHead>
                <TableHead className="text-right">Overtime</TableHead>
                <TableHead className="text-right">Double</TableHead>
                <TableHead className="text-right">Holiday</TableHead>
                <TableHead className="text-right">Total h</TableHead>
                <TableHead className="text-right">Gross</TableHead>
                <TableHead>Approved by</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {p.rows.map((r) => (
                <TableRow key={r.timesheet_id}>
                  <TableCell>
                    <Link
                      to="/timesheets/$timesheetId"
                      params={{ timesheetId: r.timesheet_id }}
                      className="font-medium hover:underline"
                    >
                      {r.employee_name}
                    </Link>
                    <span className="block text-xs text-muted-foreground">{r.employee_code}</span>
                  </TableCell>
                  <HoursCell
                    hours={r.regular_hours}
                    amount={r.regular_amount}
                    currency={r.currency ?? p.currency}
                  />
                  <HoursCell
                    hours={r.overtime_hours}
                    amount={r.overtime_amount}
                    currency={r.currency ?? p.currency}
                  />
                  <HoursCell
                    hours={r.double_time_hours}
                    amount={r.double_time_amount}
                    currency={r.currency ?? p.currency}
                  />
                  <HoursCell
                    hours={r.holiday_hours}
                    amount={r.holiday_amount}
                    currency={r.currency ?? p.currency}
                  />
                  <TableCell className="tabular text-right font-medium">
                    {formatHours(r.total_hours)}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    <Money amount={r.gross_amount} currency={r.currency ?? p.currency} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {r.approved_by ?? "—"}
                    {r.approved_at ? (
                      <span className="block text-xs">{formatDateTime(r.approved_at)}</span>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="bg-muted/40 font-semibold hover:bg-muted/40">
                <TableCell>Totals</TableCell>
                <HoursCell
                  hours={p.totals.regular_hours}
                  amount={p.totals.regular_amount}
                  currency={p.currency}
                />
                <HoursCell
                  hours={p.totals.overtime_hours}
                  amount={p.totals.overtime_amount}
                  currency={p.currency}
                />
                <HoursCell
                  hours={p.totals.double_time_hours}
                  amount={p.totals.double_time_amount}
                  currency={p.currency}
                />
                <HoursCell
                  hours={p.totals.holiday_hours}
                  amount={p.totals.holiday_amount}
                  currency={p.currency}
                />
                <TableCell className="tabular text-right">
                  {formatHours(p.totals.total_hours)}
                </TableCell>
                <TableCell className="text-right">
                  <Money amount={p.totals.gross_amount} currency={p.currency} />
                </TableCell>
                <TableCell />
              </TableRow>
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function HoursCell({
  hours,
  amount,
  currency,
}: {
  hours: number;
  amount: number | null;
  currency: string | null;
}): JSX.Element {
  return (
    <TableCell className="text-right">
      <span className="tabular block">{formatHours(hours)}</span>
      {hours > 0 || amount ? (
        <span className="block text-xs text-muted-foreground">
          <Money amount={amount} currency={currency} />
        </span>
      ) : null}
    </TableCell>
  );
}

function Warnings({ p }: { p: ExportPreview }): JSX.Element | null {
  const items: string[] = [];
  if (p.pending_review > 0)
    items.push(
      `${p.pending_review} timesheet${p.pending_review === 1 ? "" : "s"} for this week still need review and won't be included.`,
    );
  if (p.rejected > 0)
    items.push(`${p.rejected} rejected timesheet${p.rejected === 1 ? " is" : "s are"} left out.`);
  if (p.already_exported > 0)
    items.push(
      `${p.already_exported} timesheet${p.already_exported === 1 ? " was" : "s were"} already exported earlier and won't be exported again.`,
    );
  if (items.length === 0) return null;
  return (
    <Banner tone="warning">
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
      {p.pending_review > 0 ? (
        <Link
          to="/review"
          search={{ status: "needs_review", company_id: p.company_id }}
          className="mt-1 inline-block font-medium underline"
        >
          Review them now
        </Link>
      ) : null}
    </Banner>
  );
}

function History({ companyId }: { companyId?: string }): JSX.Element {
  const [page, setPage] = useState(1);
  const params = { company_id: companyId, page, size: 10 };
  const q = useExportHistory(params);
  const companies = useCompanyMap();
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>
          Export history{companyId ? ` · ${companies.get(companyId)?.name ?? ""}` : ""}
        </CardTitle>
      </CardHeader>
      {q.isPending ? (
        <TableSkeleton rows={4} cols={6} />
      ) : q.isError ? (
        <CardContent>
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </CardContent>
      ) : q.data.items.length === 0 ? (
        <CardContent>
          <p className="text-sm text-muted-foreground">No payroll sheets created yet.</p>
        </CardContent>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Week</TableHead>
                <TableHead className="text-right">Rows</TableHead>
                <TableHead className="text-right">Gross</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Download</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.items.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-medium">{b.company_name}</TableCell>
                  <TableCell>{formatWeek(b.week_start)}</TableCell>
                  <TableCell className="tabular text-right">{b.row_count}</TableCell>
                  <TableCell className="text-right">
                    <Money amount={b.gross_amount} currency={b.currency} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(b.created_at)}
                    {b.created_by_name ? (
                      <span className="block text-xs">{b.created_by_name}</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <DownloadButtons batch={b} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination page={page} size={10} total={q.data.total} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

/** The page's search params, checked when the URL changes. */
