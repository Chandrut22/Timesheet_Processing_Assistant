// A timesheet whose sheet gave only a weekly total ("Saran - 42 h", no days): what was
// paid and why, and the week it is booked in, which the reviewer can change (it is
// assumed when the sheet and the email name no dates). Entering days below turns it into
// a normal timesheet.
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import type { TimesheetRead } from "@/api/models";
import { FormError } from "@/components/Field";
import { Banner } from "@/components/States";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { backendWeekday, formatHours, formatWeek, WEEKDAYS } from "@/lib/format";
import { hasFlag } from "@/lib/severity";
import { useTimesheetMutation } from "./useTimesheetMutation";

export function WeeklyTotalPanel({
  t,
  weekStartDay,
  readOnly,
}: {
  t: TimesheetRead;
  /** The company's first day of the week (0 = Monday), or undefined when unknown. */
  weekStartDay: number | undefined;
  readOnly: boolean;
}) {
  const [week, setWeek] = useState(t.week_start ?? "");
  const save = useTimesheetMutation((w: string) => coreApi.setWeek(t.id, w), {
    success: "Week changed.",
    silentError: true,
  });
  const assumed = hasFlag(t.flags, "week_assumed");
  const startDay = weekStartDay ?? 0;
  const wrongDay = week !== "" && backendWeekday(week) !== startDay;
  const changed = week !== (t.week_start ?? "");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="size-4 text-muted-foreground" aria-hidden /> Weekly total only
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p>
          The sheet gives <strong>{formatHours(t.stated_total)} h</strong> for the week and no daily
          hours. It is paid as {formatHours(t.regular_hours)} h regular
          {t.overtime_hours > 0 ? ` + ${formatHours(t.overtime_hours)} h overtime` : ""} under the
          company's weekly limit. Daily overtime, double time and holidays could not be applied: add
          the days below if you know them.
        </p>

        {assumed ? (
          <Banner tone="warning">
            No dates on the sheet or in the email: the week is assumed to be the last full week
            before it arrived ({formatWeek(t.week_start)}). Check it before approving.
          </Banner>
        ) : null}

        {readOnly ? (
          <p className="text-muted-foreground">Week {formatWeek(t.week_start)}</p>
        ) : (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (changed && !wrongDay) save.mutate(week);
            }}
          >
            <div className="grid gap-1.5">
              <Label htmlFor="weekly-total-week">Week starting</Label>
              <Input
                id="weekly-total-week"
                type="date"
                className="w-44"
                value={week}
                aria-invalid={wrongDay}
                aria-describedby="weekly-total-week-hint"
                onChange={(e) => setWeek(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              variant="outline"
              disabled={!changed || wrongDay || save.isPending}
            >
              {save.isPending ? "Saving…" : "Change week"}
            </Button>
            <p
              id="weekly-total-week-hint"
              className={wrongDay ? "w-full text-destructive" : "w-full text-muted-foreground"}
            >
              {wrongDay
                ? `Weeks start on ${WEEKDAYS[startDay]} for this company: pick a ${WEEKDAYS[startDay]}.`
                : `Weeks start on ${WEEKDAYS[startDay]}.`}
            </p>
          </form>
        )}
        <FormError message={save.error ? errorMessage(save.error) : null} />
      </CardContent>
    </Card>
  );
}
