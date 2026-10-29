import { zodResolver } from "@hookform/resolvers/zod";
import { CopyPlus, Plus, Save, Trash2, Undo2 } from "lucide-react";
import { useState, type JSX } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { errorMessage } from "@/services/apiErrors";
import type { TimesheetRead } from "../types/timesheet";
import { FormError } from "@/components/forms/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { applyFieldErrors } from "@/lib/forms";
import { daysBetween, formatDayLabel, formatHours, formatWeek, shiftIsoDate } from "@/utils/format";
import { useTimesheetMutation } from "../hooks/useTimesheetMutation";
import { timesheetService } from "../services/timesheetService";

const ISO = /^\d{4}-\d{2}-\d{2}$/;

const rowSchema = z.object({
  work_date: z.string().regex(ISO, "Pick a date"),
  hours: z
    .number({ error: "Enter hours" })
    .min(0, "Between 0 and 24")
    .max(24, "Between 0 and 24")
    .refine((h) => Number.isInteger(Math.round(h * 1000) / 250), "Use steps of 0.25"),
  double_time_marked: z.boolean(),
  /** The holiday checkbox edits sheet_holiday (what the sheet said). */
  sheet_holiday: z.boolean(),
  note: z.string().max(255, "At most 255 characters"),
});

// The form's shape; makeSchema adds the checks that need the week (zod 4 refinements
// keep the schema's type).
const entriesBase = z.object({ entries: z.array(rowSchema).max(31, "At most 31 days") });

function makeSchema(weekStart: string | null): typeof entriesBase {
  return entriesBase.superRefine(({ entries }, ctx) => {
    const seen = new Map<string, number>();
    entries.forEach((e, i) => {
      if (!ISO.test(e.work_date)) return;
      if (seen.has(e.work_date)) {
        ctx.addIssue({
          code: "custom",
          path: ["entries", i, "work_date"],
          message: "This day is already listed",
        });
      }
      seen.set(e.work_date, i);
    });
    const dates = entries
      .map((e) => e.work_date)
      .filter((d) => ISO.test(d))
      .sort();
    if (dates.length === 0) return;
    const anchor = weekStart ?? dates[0];
    entries.forEach((e, i) => {
      if (!ISO.test(e.work_date)) return;
      const diff = daysBetween(anchor, e.work_date);
      if (diff === null || diff < 0 || diff > 6) {
        ctx.addIssue({
          code: "custom",
          path: ["entries", i, "work_date"],
          message: weekStart
            ? `Must be in the week of ${formatWeek(weekStart)}`
            : "All days must be in one week",
        });
      }
    });
  });
}

type Values = { entries: z.infer<typeof rowSchema>[] };

function toValues(t: TimesheetRead): Values {
  return {
    entries: [...t.entries]
      .sort((a, b) => a.work_date.localeCompare(b.work_date))
      .map((e) => ({
        work_date: e.work_date,
        hours: Number(e.hours),
        double_time_marked: e.double_time_marked,
        sheet_holiday: e.sheet_holiday,
        note: e.note ?? "",
      })),
  };
}

/**
 * The editable days table. Parent should give it key={…entries…} so it resets
 * when the timesheet changes on the server.
 */
export function EntriesEditor({
  timesheet,
  readOnly,
}: {
  timesheet: TimesheetRead;
  readOnly: boolean;
}): JSX.Element {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(makeSchema(timesheet.week_start)),
    defaultValues: toValues(timesheet),
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "entries" });
  const watched = useWatch({ control: form.control, name: "entries" });
  const errors = form.formState.errors.entries;
  const listErrorBox = errors as { message?: string; root?: { message?: string } } | undefined;
  const listError = listErrorBox?.message ?? listErrorBox?.root?.message;
  const finalHoliday = new Map(timesheet.entries.map((e) => [e.work_date, e.is_holiday]));

  const save = useTimesheetMutation(
    ({ values, newVersion }: { values: Values; newVersion: boolean }) =>
      timesheetService.updateEntries(
        timesheet.id,
        values.entries.map((e) => ({
          work_date: e.work_date,
          hours: e.hours,
          double_time_marked: e.double_time_marked,
          is_holiday: e.sheet_holiday,
          note: e.note.trim() || null,
        })),
        newVersion,
      ),
    {
      success: (t, { newVersion }) =>
        newVersion
          ? `Saved as version ${t.version}. Version ${t.version - 1} is kept in the history.`
          : "Days saved. Hours and pay were recalculated.",
      silentError: true,
    },
  );

  /** Save: the change goes into the current version. As new version: the old data is kept. */
  const submit = (newVersion: boolean): ReturnType<typeof form.handleSubmit> =>
    form.handleSubmit((values) => {
      setFormError(null);
      save.mutate(
        { values, newVersion },
        {
          onError: (err) => {
            // 422 (e.g. "all days must be in one week") is shown as the backend wrote it.
            applyFieldErrors(err, form.setError, ["entries"]);
            setFormError(errorMessage(err));
          },
        },
      );
    });
  const onSubmit = submit(false);
  const savingAsNew = save.isPending && save.variables?.newVersion === true;

  const total = (watched ?? []).reduce(
    (sum, e) => sum + (Number.isFinite(e?.hours) ? e.hours : 0),
    0,
  );
  const dirty = form.formState.isDirty;

  const addDay = (): void => {
    const dates = (watched ?? [])
      .map((e) => e.work_date)
      .filter((d) => ISO.test(d))
      .sort();
    const next = dates.length
      ? shiftIsoDate(dates[dates.length - 1], 1)
      : (timesheet.week_start ?? "");
    append({
      work_date: next,
      hours: 0,
      double_time_marked: false,
      sheet_holiday: false,
      note: "",
    });
  };

  return (
    <Card>
      <form onSubmit={onSubmit} noValidate>
        <CardHeader>
          <div>
            <CardTitle>Days</CardTitle>
            <CardDescription>
              {readOnly
                ? "This timesheet can't be edited."
                : `Fix what the assistant read. Saving recalculates hours and pay and updates version ${timesheet.version}; "Create as new version" keeps version ${timesheet.version} in the history.`}
            </CardDescription>
          </div>
          <div className="text-right text-sm">
            <span className="text-muted-foreground">Total </span>
            <span className="tabular font-semibold">{formatHours(total)} h</span>
            {dirty ? (
              <span className="block text-xs text-muted-foreground">
                saved: {formatHours(timesheet.total_hours)} h
              </span>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {formError ? (
            <div className="px-5 pb-3">
              <FormError message={formError} />
            </div>
          ) : null}
          {listError ? (
            <div className="px-5 pb-3">
              <FormError message={listError} />
            </div>
          ) : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-44">Date</TableHead>
                <TableHead className="w-28">Hours</TableHead>
                <TableHead className="w-24 text-center">Double time</TableHead>
                <TableHead className="w-28 text-center">Holiday (sheet)</TableHead>
                <TableHead>Note</TableHead>
                {!readOnly ? <TableHead className="w-10" /> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {fields.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">
                    No days on this timesheet.
                  </TableCell>
                </TableRow>
              ) : null}
              {fields.map((field, i) => {
                const rowErr = errors?.[i];
                const date = watched?.[i]?.work_date ?? field.work_date;
                const calendarHoliday =
                  finalHoliday.get(date) === true && !watched?.[i]?.sheet_holiday;
                return (
                  <TableRow key={field.id}>
                    <TableCell className="align-top">
                      {readOnly ? (
                        <span>{formatDayLabel(date)}</span>
                      ) : (
                        <Input
                          type="date"
                          aria-label={`Day ${i + 1} date`}
                          aria-invalid={!!rowErr?.work_date}
                          {...form.register(`entries.${i}.work_date`)}
                        />
                      )}
                      {rowErr?.work_date ? (
                        <p className="mt-1 text-xs whitespace-normal text-destructive">
                          {rowErr.work_date.message}
                        </p>
                      ) : (
                        !readOnly && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            {formatDayLabel(date)}
                          </p>
                        )
                      )}
                      {finalHoliday.get(date) ? (
                        <Badge
                          variant="info"
                          className="mt-1"
                          title="Final value used for pay (includes calendar holidays)"
                        >
                          {calendarHoliday ? "Calendar holiday" : "Holiday"}
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell className="align-top">
                      {readOnly ? (
                        <span className="tabular">{formatHours(watched?.[i]?.hours)}</span>
                      ) : (
                        <Input
                          type="number"
                          inputMode="decimal"
                          step={0.25}
                          min={0}
                          max={24}
                          aria-label={`Day ${i + 1} hours`}
                          aria-invalid={!!rowErr?.hours}
                          className="tabular"
                          {...form.register(`entries.${i}.hours`, { valueAsNumber: true })}
                        />
                      )}
                      {rowErr?.hours ? (
                        <p className="mt-1 text-xs whitespace-normal text-destructive">
                          {rowErr.hours.message}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-center align-top">
                      <Checkbox
                        aria-label={`Day ${i + 1} double time`}
                        disabled={readOnly}
                        className="mt-2.5"
                        {...form.register(`entries.${i}.double_time_marked`)}
                      />
                    </TableCell>
                    <TableCell className="text-center align-top">
                      <Checkbox
                        aria-label={`Day ${i + 1} marked as holiday on the sheet`}
                        disabled={readOnly}
                        className="mt-2.5"
                        {...form.register(`entries.${i}.sheet_holiday`)}
                      />
                    </TableCell>
                    <TableCell className="align-top">
                      {readOnly ? (
                        <span className="whitespace-normal text-muted-foreground">
                          {watched?.[i]?.note || "—"}
                        </span>
                      ) : (
                        <Input
                          aria-label={`Day ${i + 1} note`}
                          maxLength={255}
                          {...form.register(`entries.${i}.note`)}
                        />
                      )}
                      {rowErr?.note ? (
                        <p className="mt-1 text-xs text-destructive">{rowErr.note.message}</p>
                      ) : null}
                    </TableCell>
                    {!readOnly ? (
                      <TableCell className="align-top">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Remove day ${i + 1}`}
                          onClick={() => remove(i)}
                        >
                          <Trash2 />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {!readOnly ? (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-3">
              <Button variant="outline" size="sm" onClick={addDay} disabled={fields.length >= 31}>
                <Plus /> Add day
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!dirty || save.isPending}
                  onClick={() => {
                    setFormError(null);
                    form.reset(toValues(timesheet));
                  }}
                >
                  <Undo2 /> Undo changes
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!dirty || save.isPending}
                  onClick={() => void submit(true)()}
                >
                  <CopyPlus /> {savingAsNew ? "Saving…" : "Create as new version"}
                </Button>
                <Button type="submit" size="sm" disabled={!dirty || save.isPending}>
                  <Save /> {save.isPending && !savingAsNew ? "Saving…" : "Save days"}
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </form>
    </Card>
  );
}
