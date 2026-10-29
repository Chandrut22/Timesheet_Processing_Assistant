import { useQuery } from "@tanstack/react-query";
import { Check, Search } from "lucide-react";
import { useRef, useState, type JSX } from "react";
import { errorMessage } from "@/services/apiErrors";
import {
  type EmployeeRead,
  useEmployeeMap,
  employeeService,
  employeeKeys,
} from "@/features/employees";
import type { TimesheetRead } from "../types/timesheet";
import { FormError } from "@/components/forms/Field";
import { ErrorState } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/useDebounce";
import { formatDate } from "@/utils/format";
import { flagCandidates } from "../utils/severity";
import { cn } from "@/lib/utils";
import { useTimesheetMutation } from "../hooks/useTimesheetMutation";
import { timesheetService } from "../services/timesheetService";

export function MatchEmployeeDialog({
  t,
  open,
  onOpenChange,
  onMatchNext,
}: {
  t: TimesheetRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Shows "Match & next unmatched": after the match, called instead of closing. */
  onMatchNext?: () => void;
}): JSX.Element {
  const goNext = useRef(false);
  const [q, setQ] = useState(t.extracted_name ?? "");
  // A close-spelling match is only a suggestion: it is pre-selected, so "Match" confirms it.
  const fuzzy = t.match_method === "fuzzy";
  const [chosen, setChosen] = useState<string | null>(fuzzy ? t.employee_id : null);
  const query = useDebounce(q.trim());
  const params = {
    company_id: t.company_id ?? undefined,
    q: query || undefined,
    size: 20,
    page: 1,
  };
  const results = useQuery({
    queryKey: employeeKeys.list(params),
    queryFn: ({ signal }) => employeeService.listEmployees(params, signal),
    enabled: open,
  });
  const companyEmployees = useEmployeeMap([t.company_id]);
  const candidates = flagCandidates(t.flags).filter((c) => fuzzy || c.id !== t.employee_id);

  const m = useTimesheetMutation(
    (employeeId: string) => timesheetService.matchEmployee(t.id, employeeId),
    {
      success: "Employee matched. Pay was recalculated.",
      silentError: true,
      onSuccess: () => {
        if (goNext.current && onMatchNext) onMatchNext();
        else onOpenChange(false);
      },
    },
  );

  const row = (
    e: Pick<EmployeeRead, "id" | "full_name" | "employee_code"> & Partial<EmployeeRead>,
    suggested = false,
  ): JSX.Element => (
    <li key={`${suggested ? "s" : "r"}-${e.id}`}>
      <button
        type="button"
        onClick={() => setChosen(e.id)}
        aria-pressed={chosen === e.id}
        className={cn(
          "flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
          chosen === e.id && "border-primary bg-primary/5",
        )}
      >
        <span className="min-w-0">
          <span className="block truncate font-medium">{e.full_name}</span>
          <span className="block text-xs text-muted-foreground">
            {e.employee_code}
            {e.email ? ` · ${e.email}` : ""}
            {e.assignment_start ? ` · from ${formatDate(e.assignment_start)}` : ""}
            {e.assignment_end ? ` to ${formatDate(e.assignment_end)}` : ""}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {suggested ? (
            <Badge variant="info">
              {fuzzy && e.id === t.employee_id ? "Suggested · close spelling" : "Suggested"}
            </Badge>
          ) : null}
          {e.is_active === false ? <Badge variant="muted">Inactive</Badge> : null}
          {chosen === e.id ? <Check className="size-4 text-primary" /> : null}
        </span>
      </button>
    </li>
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) m.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>Match employee</DialogTitle>
          <DialogDescription>
            The sheet says «{t.extracted_name ?? "no name"}»
            {t.extracted_code ? ` (${t.extracted_code})` : ""}. Pick the employee this timesheet
            belongs to.
          </DialogDescription>
        </DialogHeader>

        <FormError message={m.error ? errorMessage(m.error) : null} />

        {candidates.length > 0 ? (
          <section>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Suggestions
            </h3>
            <ul className="grid gap-1.5">
              {candidates.map((c) => {
                const e = companyEmployees.get(c.id);
                return row(
                  e ?? { id: c.id, full_name: c.label ?? "Suggested employee", employee_code: "" },
                  true,
                );
              })}
            </ul>
          </section>
        ) : null}

        <section className="grid gap-2">
          <label
            htmlFor="match-search"
            className="text-xs font-medium tracking-wide text-muted-foreground uppercase"
          >
            Search {t.company_id ? "this company's" : "all"} employees
          </label>
          <div className="relative">
            <Search
              className="absolute top-2.5 left-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="match-search"
              className="pl-8"
              placeholder="Name or code"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          {results.isPending ? (
            <Skeleton className="h-24" />
          ) : results.isError ? (
            <ErrorState error={results.error} onRetry={() => void results.refetch()} />
          ) : results.data.items.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No employees found. Check the spelling, or add the employee first.
            </p>
          ) : (
            <ul className="grid max-h-72 gap-1.5 overflow-y-auto">
              {results.data.items.map((e) => row(e))}
            </ul>
          )}
        </section>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={m.isPending}>
            Cancel
          </Button>
          {onMatchNext ? (
            <Button
              variant="outline"
              onClick={() => {
                if (!chosen) return;
                goNext.current = true;
                m.mutate(chosen);
              }}
              disabled={!chosen || m.isPending}
            >
              Match &amp; next unmatched
            </Button>
          ) : null}
          <Button
            onClick={() => {
              if (!chosen) return;
              goNext.current = false;
              m.mutate(chosen);
            }}
            disabled={!chosen || m.isPending}
          >
            {m.isPending ? "Matching…" : "Match"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
