import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { CompanyRead } from "../types/company";
import { Field, FormError } from "@/components/forms/Field";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, NativeSelect } from "@/components/ui/input";
import { applyFieldErrors } from "@/lib/forms";
import { splitList, WEEKDAYS } from "@/utils/format";

const AMOUNT = /^\d+(\.\d{1,2})?$/;
const NUMBER = /^\d+(\.\d+)?$/;

const money = z
  .string()
  .trim()
  .refine((v) => AMOUNT.test(v) && Number(v) > 0, "Enter an amount above 0, like 450.00");
const optionalMoney = z
  .string()
  .trim()
  .refine(
    (v) => v === "" || (AMOUNT.test(v) && Number(v) > 0),
    "Enter an amount above 0, or leave it empty",
  );
const hours = (max: number) =>
  z
    .string()
    .trim()
    .refine(
      (v) => NUMBER.test(v) && Number(v) > 0 && Number(v) <= max,
      `More than 0 and at most ${max}`,
    );
const optionalHours = (max: number) =>
  z
    .string()
    .trim()
    .refine(
      (v) => v === "" || (NUMBER.test(v) && Number(v) > 0 && Number(v) <= max),
      `More than 0 and at most ${max}, or leave it empty`,
    );

const schema = z
  .object({
    name: z.string().trim().min(1, "Enter the company name").max(200),
    aliases: z.string(),
    currency: z
      .string()
      .trim()
      .regex(/^[A-Za-z]{3}$/, "A 3-letter code like INR"),
    hourly_rate: money,
    overtime_rate: money,
    double_time_rate: optionalMoney,
    holiday_rate: money,
    daily_ot_after: hours(24),
    weekly_ot_after: hours(168),
    double_time_after: optionalHours(24),
    week_start: z.string().regex(/^[0-6]$/),
    is_active: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.double_time_after && !v.double_time_rate) {
      ctx.addIssue({
        code: "custom",
        path: ["double_time_rate"],
        message: "Needed when there's a double-time rule",
      });
    }
    if (splitList(v.aliases).length > 20) {
      ctx.addIssue({ code: "custom", path: ["aliases"], message: "At most 20 other names" });
    }
  });

export type CompanyFormValues = z.infer<typeof schema>;

const FIELDS = [
  "name",
  "aliases",
  "currency",
  "hourly_rate",
  "overtime_rate",
  "double_time_rate",
  "holiday_rate",
  "daily_ot_after",
  "weekly_ot_after",
  "double_time_after",
  "week_start",
  "is_active",
] as const;

function toValues(c?: CompanyRead): CompanyFormValues {
  const s = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));
  return {
    name: c?.name ?? "",
    aliases: c?.aliases.join(", ") ?? "",
    currency: c?.currency ?? "INR",
    hourly_rate: s(c?.hourly_rate),
    overtime_rate: s(c?.overtime_rate),
    double_time_rate: s(c?.double_time_rate),
    holiday_rate: s(c?.holiday_rate),
    daily_ot_after: c ? s(c.daily_ot_after) : "8",
    weekly_ot_after: c ? s(c.weekly_ot_after) : "40",
    double_time_after: s(c?.double_time_after),
    week_start: String(c?.week_start ?? 0),
    is_active: c?.is_active ?? true,
  };
}

export function CompanyForm({
  company,
  readOnly = false,
  submitLabel,
  onSubmit,
  onCancel,
  serverError,
}: {
  company?: CompanyRead;
  readOnly?: boolean;
  submitLabel: string;
  onSubmit: (values: CompanyFormValues) => Promise<unknown>;
  onCancel?: () => void;
  serverError?: string | null;
}) {
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(company),
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  const reg = form.register;

  const submit = form.handleSubmit(async (v) => {
    try {
      await onSubmit(v);
      form.reset(v);
    } catch (err) {
      applyFieldErrors(err, form.setError, FIELDS);
    }
  });

  return (
    <form onSubmit={submit} noValidate>
      <fieldset disabled={readOnly || isSubmitting} className="grid gap-5">
        <FormError message={serverError} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="c-name" error={errors.name?.message}>
            <Input id="c-name" aria-invalid={!!errors.name} {...reg("name")} />
          </Field>
          <Field
            label="Other names"
            htmlFor="c-aliases"
            error={errors.aliases?.message}
            hint="Separate with commas. Helps match timesheets that spell the name differently."
          >
            <Input id="c-aliases" {...reg("aliases")} />
          </Field>
        </div>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Pay rates (per hour)</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Field label="Currency" htmlFor="c-currency" error={errors.currency?.message}>
              <Input id="c-currency" maxLength={3} className="uppercase" {...reg("currency")} />
            </Field>
            <Field label="Regular" htmlFor="c-hourly" error={errors.hourly_rate?.message}>
              <Input
                id="c-hourly"
                inputMode="decimal"
                className="tabular"
                {...reg("hourly_rate")}
              />
            </Field>
            <Field label="Overtime" htmlFor="c-ot" error={errors.overtime_rate?.message}>
              <Input id="c-ot" inputMode="decimal" className="tabular" {...reg("overtime_rate")} />
            </Field>
            <Field
              label="Double time"
              htmlFor="c-dt"
              error={errors.double_time_rate?.message}
              hint="Optional"
            >
              <Input
                id="c-dt"
                inputMode="decimal"
                className="tabular"
                {...reg("double_time_rate")}
              />
            </Field>
            <Field label="Holiday" htmlFor="c-hol" error={errors.holiday_rate?.message}>
              <Input id="c-hol" inputMode="decimal" className="tabular" {...reg("holiday_rate")} />
            </Field>
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Rules</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field
              label="Overtime after (hours a day)"
              htmlFor="c-daily"
              error={errors.daily_ot_after?.message}
            >
              <Input
                id="c-daily"
                inputMode="decimal"
                className="tabular"
                {...reg("daily_ot_after")}
              />
            </Field>
            <Field
              label="Overtime after (hours a week)"
              htmlFor="c-weekly"
              error={errors.weekly_ot_after?.message}
            >
              <Input
                id="c-weekly"
                inputMode="decimal"
                className="tabular"
                {...reg("weekly_ot_after")}
              />
            </Field>
            <Field
              label="Double time after (hours a day)"
              htmlFor="c-dta"
              error={errors.double_time_after?.message}
              hint="Leave empty for no double-time rule"
            >
              <Input
                id="c-dta"
                inputMode="decimal"
                className="tabular"
                {...reg("double_time_after")}
              />
            </Field>
            <Field label="Week starts on" htmlFor="c-week" error={errors.week_start?.message}>
              <NativeSelect id="c-week" {...reg("week_start")}>
                {WEEKDAYS.map((d, i) => (
                  <option key={d} value={String(i)}>
                    {d}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
        </section>

        {company ? (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox {...reg("is_active")} />
            Active (inactive companies' emails are no longer accepted)
          </label>
        ) : null}

        {!readOnly ? (
          <div className="flex flex-wrap justify-end gap-2">
            {onCancel ? (
              <Button variant="outline" onClick={onCancel}>
                Cancel
              </Button>
            ) : null}
            <Button type="submit" disabled={isSubmitting || (!!company && !isDirty)}>
              {isSubmitting ? "Saving…" : submitLabel}
            </Button>
          </div>
        ) : null}
      </fieldset>
    </form>
  );
}
