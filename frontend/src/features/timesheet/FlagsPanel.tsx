import { Link } from "@tanstack/react-router";
import { CircleCheck } from "lucide-react";
import type { FlagRead } from "@/api/models";
import { SeverityBadge } from "@/components/Badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { humanize } from "@/lib/format";
import { groupFlags, otherTimesheetId } from "@/lib/severity";
import { cn } from "@/lib/utils";

const ROW_TONE = {
  high: "border-l-red-500 bg-red-50/60",
  medium: "border-l-amber-500 bg-amber-50/60",
  low: "border-l-sky-500 bg-sky-50/60",
} as const;

export function FlagsPanel({ flags }: { flags: FlagRead[] }) {
  const groups = groupFlags(flags);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Flags</CardTitle>
        <span className="text-sm text-muted-foreground tabular">{flags.length}</span>
      </CardHeader>
      <CardContent>
        {flags.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-emerald-700">
            <CircleCheck className="size-4" /> No problems found.
          </p>
        ) : (
          <ul className="space-y-2">
            {(["high", "medium", "low"] as const).flatMap((sev) =>
              groups[sev].map((f, i) => {
                const other = otherTimesheetId(f);
                return (
                  <li key={`${sev}-${f.code}-${i}`} className={cn("rounded-md border border-l-4 px-3 py-2", ROW_TONE[sev])}>
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={sev} />
                      <span className="text-xs font-medium text-muted-foreground">{humanize(f.code)}</span>
                    </div>
                    <p className="mt-1 text-sm">{f.message}</p>
                    {other ? (
                      <Link
                        to="/timesheets/$timesheetId"
                        params={{ timesheetId: other }}
                        className="mt-1 inline-block text-sm text-primary hover:underline"
                      >
                        Open the other timesheet
                      </Link>
                    ) : null}
                  </li>
                );
              }),
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
