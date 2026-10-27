// The "Match" (unmatched row) / "Change" (matched row) button under the
// employee's name. Nothing for an exported timesheet: it can no longer change.
import { UserRoundSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TimesheetRead } from "../types/timesheet";
import { canMatch } from "../utils/match";

export function MatchAction({
  t,
  name,
  onMatch,
  disabled = false,
}: {
  t: Pick<TimesheetRead, "employee_id" | "status"> & Partial<Pick<TimesheetRead, "match_method">>;
  name: string;
  onMatch: () => void;
  /** e.g. while the submission is still being processed. */
  disabled?: boolean;
}) {
  if (!canMatch(t) || disabled) return null;
  if (t.employee_id !== null && t.match_method === "fuzzy") {
    // Matched by a close spelling: only a suggestion until a reviewer confirms it.
    return (
      <Button
        size="sm"
        variant="outline"
        className="mt-1 h-7 border-amber-300 px-2 text-xs text-amber-900"
        onClick={onMatch}
        aria-label={`Confirm employee (close spelling: ${name})`}
      >
        <UserRoundSearch aria-hidden />
        Confirm match
      </Button>
    );
  }
  if (t.employee_id === null) {
    return (
      <Button
        size="sm"
        variant="outline"
        className="mt-1 h-7 px-2 text-xs"
        onClick={onMatch}
        aria-label={`Match employee for «${name}»`}
      >
        <UserRoundSearch aria-hidden />
        Match
      </Button>
    );
  }
  return (
    <button
      type="button"
      onClick={onMatch}
      aria-label={`Change employee (now ${name})`}
      className="ml-2 text-xs text-muted-foreground underline-offset-2 opacity-0 group-hover:opacity-100 hover:text-foreground hover:underline focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      Change
    </button>
  );
}
