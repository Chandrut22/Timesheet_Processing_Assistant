import { getRouteApi, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { SlidersHorizontal, RotateCcw } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  TIMESHEET_STATUSES,
  type TimesheetRead,
  type TimesheetSort,
  FlagBadges,
  MatchAction,
  MatchEmployeeDialog,
  nextUnmatched,
  SeverityDot,
  TimesheetStatusBadge,
  timesheetCompanyName,
  timesheetEmployeeName,
  timesheetService,
  timesheetKeys,
} from "@/features/timesheets";
import { CompanySelect, useCompanyMap } from "@/features/companies";
import { Money } from "@/components/common/Money";
import { PageHeader } from "@/components/common/PageHeader";
import { Pagination } from "@/components/common/Pagination";
import { SortHeader } from "@/components/common/SortHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input, Label, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BulkBar } from "./BulkActions";
import { DebouncedInput } from "@/components/forms/DebouncedInput";
import {
  advancedFilterCount,
  nextReviewSearch,
  REVIEW_DEFAULTS,
  reviewParams,
  type ReviewSearch,
} from "../utils/search";
import { formatDate, formatHours, formatPercent, formatWeek, humanize } from "@/utils/format";
import { useEmployeeMap } from "@/features/employees";
import { BackButton } from "@/components/common/BackButton";

const routeApi = getRouteApi("/_app/review");

const LOCKED = new Set(["exported"]);
const EMPTY: Set<string> = new Set();

export function ReviewQueuePage() {
  const search = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const params = useMemo(() => reviewParams(search), [search]);
  const [showMore, setShowMore] = useState(advancedFilterCount(search) > 0);
  // Selection only applies to the list on screen: it resets when the filters change.
  const paramsKey = JSON.stringify(params);
  const [selection, setSelection] = useState<{ key: string; ids: Set<string> }>({
    key: paramsKey,
    ids: new Set(),
  });
  const selected = selection.key === paramsKey ? selection.ids : EMPTY;
  const setSelected = (next: Set<string> | ((prev: Set<string>) => Set<string>)) =>
    setSelection((cur) => {
      const prev = cur.key === paramsKey ? cur.ids : EMPTY;
      return { key: paramsKey, ids: typeof next === "function" ? next(prev) : next };
    });

  const query = useQuery({
    queryKey: timesheetKeys.list(params),
    queryFn: ({ signal }) => timesheetService.listTimesheets(params, signal),
    placeholderData: keepPreviousData,
  });
  const items = useMemo(() => query.data?.items ?? [], [query.data]);
  const companies = useCompanyMap();
  const employees = useEmployeeMap(items.map((t) => t.company_id));

  /** Change filters; any change other than the page goes back to page 1. */
  const update = useCallback(
    (patch: Partial<ReviewSearch>) =>
      void navigate({ search: (prev) => nextReviewSearch(prev, patch), replace: true }),
    [navigate],
  );

  const sort = params.sort ?? REVIEW_DEFAULTS.sort;
  const order = params.order ?? REVIEW_DEFAULTS.order;
  const onSort = (key: TimesheetSort) =>
    update({ sort: key, order: sort === key && order === "desc" ? "asc" : "desc" });

  const selectable = items.filter((t) => !LOCKED.has(t.status));
  const allSelected = selectable.length > 0 && selectable.every((t) => selected.has(t.id));
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(selectable.map((t) => t.id)));
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // "Match employee" on a row. The dialog follows the row by id, so the list refreshing
  // after a match never closes it on the wrong timesheet.
  const [matchingId, setMatchingId] = useState<string | null>(null);
  const matching = matchingId ? items.find((t) => t.id === matchingId) : undefined;
  const matchNext = matching ? nextUnmatched(items, matching.id) : null;

  const labelFor = (id: string) => {
    const t = items.find((x) => x.id === id);
    return t ? timesheetEmployeeName(t, employees).name : id.slice(0, 8);
  };

  const status = search.status ?? REVIEW_DEFAULTS.status;
  const moreCount = advancedFilterCount(search);

  return (
    <>
      <PageHeader
        title="Review queue"
        back={<BackButton fallback="/" fallbackLabel="Dashboard" />}
        description="Check what the assistant read, fix it if needed, and approve or reject."
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="grid gap-1.5 lg:col-span-2">
            <Label htmlFor="f-q">Employee</Label>
            <DebouncedInput
              id="f-q"
              type="search"
              placeholder="Name or code"
              value={search.q ?? ""}
              onCommit={(q) => update({ q })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="f-status">Status</Label>
            <NativeSelect
              id="f-status"
              value={status}
              onChange={(e) => update({ status: e.target.value as ReviewSearch["status"] })}
            >
              {TIMESHEET_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
              <option value="all">All statuses</option>
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="f-sev">Severity</Label>
            <NativeSelect
              id="f-sev"
              value={search.severity ?? ""}
              onChange={(e) =>
                update({ severity: (e.target.value || undefined) as ReviewSearch["severity"] })
              }
            >
              <option value="">Any</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="none">No flags</option>
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="f-company">Company</Label>
            <CompanySelect
              id="f-company"
              value={search.company_id ?? ""}
              onChange={(company_id) => update({ company_id })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="f-matched">Employee match</Label>
            <NativeSelect
              id="f-matched"
              value={search.matched ?? ""}
              onChange={(e) =>
                update({ matched: (e.target.value || undefined) as ReviewSearch["matched"] })
              }
            >
              <option value="">Any</option>
              <option value="yes">Matched</option>
              <option value="no">Unmatched</option>
            </NativeSelect>
          </div>
        </div>

        {showMore ? (
          <div className="mt-3 grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-6">
            <div className="grid gap-1.5">
              <Label htmlFor="f-flag">Has flag</Label>
              <DebouncedInput
                id="f-flag"
                placeholder="e.g. conflicting_hours"
                value={search.flag ?? ""}
                onCommit={(flag) => update({ flag })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="f-sender">Sender</Label>
              <DebouncedInput
                id="f-sender"
                placeholder="Part of the email"
                value={search.sender ?? ""}
                onCommit={(sender) => update({ sender })}
              />
            </div>
            <DateRange
              label="Worked week"
              idPrefix="f-week"
              from={search.date_from}
              to={search.date_to}
              onChange={(date_from, date_to) => update({ date_from, date_to })}
            />
            <DateRange
              label="Received"
              idPrefix="f-recv"
              from={search.received_from}
              to={search.received_to}
              onChange={(received_from, received_to) => update({ received_from, received_to })}
            />
            <div className="grid min-w-0 gap-1.5 sm:col-span-2 lg:col-span-1">
              <span className="text-sm leading-none font-medium">Confidence %</span>
              <div className="flex min-w-0 items-center gap-1.5">
                <Input
                  aria-label="Minimum confidence percent"
                  className="min-w-0"
                  type="number"
                  min={0}
                  max={100}
                  placeholder="Min"
                  value={search.min_conf ?? ""}
                  onChange={(e) =>
                    update({ min_conf: e.target.value === "" ? undefined : Number(e.target.value) })
                  }
                />
                <span className="text-muted-foreground">–</span>
                <Input
                  aria-label="Maximum confidence percent"
                  className="min-w-0"
                  type="number"
                  min={0}
                  max={100}
                  placeholder="Max"
                  value={search.max_conf ?? ""}
                  onChange={(e) =>
                    update({ max_conf: e.target.value === "" ? undefined : Number(e.target.value) })
                  }
                />
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowMore((v) => !v)}
            aria-expanded={showMore}
          >
            <SlidersHorizontal /> {showMore ? "Fewer filters" : "More filters"}
            {moreCount > 0 ? <Badge variant="default">{moreCount}</Badge> : null}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void navigate({ search: {}, replace: true })}
          >
            <RotateCcw /> Reset filters
          </Button>
          {query.isFetching && !query.isPending ? (
            <span className="text-xs text-muted-foreground">Updating…</span>
          ) : null}
        </div>
      </Card>

      <Card>
        {query.isPending ? (
          <TableSkeleton rows={8} cols={8} />
        ) : query.isError ? (
          <div className="p-4">
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          </div>
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title={
                status === "needs_review" ? "Nothing waiting for review" : "No timesheets match"
              }
              hint="Try other filters, or reset them."
            />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      aria-label="Select all on this page"
                      checked={allSelected}
                      onChange={toggleAll}
                      disabled={selectable.length === 0}
                    />
                  </TableHead>
                  <SortHeader
                    label="Sev."
                    sortKey="severity"
                    current={sort}
                    order={order}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Employee"
                    sortKey="employee"
                    current={sort}
                    order={order}
                    onSort={onSort}
                  />
                  <TableHead>Company</TableHead>
                  <SortHeader
                    label="Week"
                    sortKey="week"
                    current={sort}
                    order={order}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Hours"
                    sortKey="hours"
                    current={sort}
                    order={order}
                    onSort={onSort}
                    className="text-right"
                  />
                  <SortHeader
                    label="Gross"
                    sortKey="gross"
                    current={sort}
                    order={order}
                    onSort={onSort}
                    className="text-right"
                  />
                  <SortHeader
                    label="Conf."
                    sortKey="confidence"
                    current={sort}
                    order={order}
                    onSort={onSort}
                    className="text-right"
                  />
                  <TableHead>Flags</TableHead>
                  <TableHead>Status</TableHead>
                  <SortHeader
                    label="Received"
                    sortKey="received"
                    current={sort}
                    order={order}
                    onSort={onSort}
                  />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((t) => (
                  <QueueRow
                    key={t.id}
                    t={t}
                    selected={selected.has(t.id)}
                    selectable={!LOCKED.has(t.status)}
                    onToggle={() => toggle(t.id)}
                    employee={timesheetEmployeeName(t, employees)}
                    company={timesheetCompanyName(t, companies)}
                    onMatch={() => setMatchingId(t.id)}
                  />
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={params.page ?? 1}
              size={params.size ?? REVIEW_DEFAULTS.size}
              total={query.data.total}
              onPage={(page) => update({ page })}
            />
          </>
        )}
      </Card>

      <BulkBar selected={[...selected]} labelFor={labelFor} onDone={() => setSelected(new Set())} />

      {matching ? (
        <MatchEmployeeDialog
          key={matching.id}
          t={matching}
          open
          onOpenChange={(o) => {
            if (!o) setMatchingId(null);
          }}
          onMatchNext={() => {
            if (matchNext) {
              setMatchingId(matchNext.id);
            } else {
              setMatchingId(null);
              toast.success("All unmatched timesheets on this page are done.");
            }
          }}
        />
      ) : null}
    </>
  );
}

function QueueRow({
  t,
  selected,
  selectable,
  onToggle,
  employee,
  company,
  onMatch,
}: {
  t: TimesheetRead;
  selected: boolean;
  selectable: boolean;
  onToggle: () => void;
  employee: { name: string; matched: boolean; code: string | null };
  company: string;
  onMatch: () => void;
}) {
  return (
    <TableRow className="group" data-state={selected ? "selected" : undefined}>
      <TableCell>
        <Checkbox
          aria-label={`Select ${employee.name}`}
          checked={selected}
          disabled={!selectable}
          onChange={onToggle}
        />
      </TableCell>
      <TableCell>
        <SeverityDot severity={t.severity} />
      </TableCell>
      <TableCell className="max-w-56">
        <Link
          to="/timesheets/$timesheetId"
          params={{ timesheetId: t.id }}
          className="block truncate font-medium hover:underline focus-visible:underline"
        >
          {employee.matched ? (
            employee.name
          ) : (
            <span className="text-amber-800">Unmatched: «{employee.name}»</span>
          )}
        </Link>
        {employee.code ? (
          <span className="text-xs text-muted-foreground">{employee.code}</span>
        ) : null}
        <MatchAction t={t} name={employee.name} onMatch={onMatch} />
      </TableCell>
      <TableCell className="max-w-48 truncate">{company}</TableCell>
      <TableCell>{formatWeek(t.week_start)}</TableCell>
      <TableCell className="tabular text-right">{formatHours(t.total_hours)}</TableCell>
      <TableCell className="text-right">
        <Money amount={t.gross_amount} currency={t.currency} />
      </TableCell>
      <TableCell className="tabular text-right">{formatPercent(t.confidence)}</TableCell>
      <TableCell className="max-w-64 whitespace-normal">
        <FlagBadges flags={t.flags} />
      </TableCell>
      <TableCell>
        <TimesheetStatusBadge status={t.status} />
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(t.created_at)}</TableCell>
    </TableRow>
  );
}

function DateRange({
  label,
  idPrefix,
  from,
  to,
  onChange,
}: {
  label: string;
  idPrefix: string;
  from?: string;
  to?: string;
  onChange: (from: string | undefined, to: string | undefined) => void;
}) {
  return (
    // Two date boxes need two columns: in one they overflowed into the next filter.
    <div className="grid min-w-0 gap-1.5 sm:col-span-2">
      <span className="text-sm leading-none font-medium">{label}</span>
      <div className="flex min-w-0 items-center gap-1.5">
        <Input
          id={`${idPrefix}-from`}
          aria-label={`${label} from`}
          className="min-w-0 flex-1"
          type="date"
          value={from ?? ""}
          onChange={(e) => onChange(e.target.value || undefined, to)}
        />
        <span className="text-muted-foreground" aria-hidden>
          –
        </span>
        <Input
          id={`${idPrefix}-to`}
          aria-label={`${label} to`}
          className="min-w-0 flex-1"
          type="date"
          value={to ?? ""}
          onChange={(e) => onChange(from, e.target.value || undefined)}
        />
      </div>
    </div>
  );
}
