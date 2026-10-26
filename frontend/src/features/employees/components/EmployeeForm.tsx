import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import type { EmployeeRead } from "../types/employee";
import { CompanySelect } from "@/features/companies";
import { Field, FormError } from "@/components/forms/Field";
import { Button } from "@/components/ui/button";
import { Checkbox, Input } from "@/components/ui/input";
import { applyFieldErrors } from "@/lib/forms";
import { splitList } from "@/utils/format";

const schema = z
  .object({
    company_id: z.string().min(1, "Choose a company"),
    employee_code: z.string().trim().min(1, "Enter the employee code").max(50),
    full_name: z.string().trim().min(1, "Enter the full name").max(200),
    email: z.union([z.literal(""), z.email("Enter a valid email address")]),
    aliases: z.string(),
    assignment_start: z.string(),
    assignment_end: z.string(),
    is_active: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.assignment_start && v.assignment_end && v.assignment_end < v.assignment_start) {
      ctx.addIssue({
        code: "custom",
        path: ["assignment_end"],
        message: "Must be on or after the start date",
      });
    }
    if (splitList(v.aliases).length > 20) {
      ctx.addIssue({ code: "custom", path: ["aliases"], message: "At most 20 other names" });
    }
  });

export type EmployeeFormValues = z.infer<typeof schema>;

const FIELDS = [
  "company_id",
  "employee_code",
  "full_name",
  "email",
  "aliases",
  "assignment_start",
  "assignment_end",
  "is_active",
] as const;

function toValues(e?: EmployeeRead, companyId?: string): EmployeeFormValues {
  return {
    company_id: e?.company_id ?? companyId ?? "",
    employee_code: e?.employee_code ?? "",
    full_name: e?.full_name ?? "",
    email: e?.email ?? "",
    aliases: e?.aliases.join(", ") ?? "",
    assignment_start: e?.assignment_start ?? "",
    assignment_end: e?.assignment_end ?? "",
    is_active: e?.is_active ?? true,
  };
}

export function EmployeeForm({
  employee,
  defaultCompanyId,
  onSubmit,
  onCancel,
  serverError,
}: {
  employee?: EmployeeRead;
  defaultCompanyId?: string;
  onSubmit: (v: EmployeeFormValues) => Promise<unknown>;
  onCancel: () => void;
  serverError?: string | null;
}) {
  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(employee, defaultCompanyId),
  });
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async (v) => {
    try {
      await onSubmit(v);
    } catch (err) {
      applyFieldErrors(err, form.setError, FIELDS);
    }
  });

  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      <FormError message={serverError} />
      <Field
        label="Company"
        htmlFor="e-company"
        error={errors.company_id?.message}
        hint={
          employee
            ? "The company can't be changed: an employee's history belongs to one company."
            : undefined
        }
      >
        <Controller
          control={form.control}
          name="company_id"
          render={({ field }) => (
            <CompanySelect
              id="e-company"
              value={field.value}
              onChange={field.onChange}
              includeAll={false}
              activeOnly={!employee}
              disabled={!!employee}
            />
          )}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Employee code" htmlFor="e-code" error={errors.employee_code?.message}>
          <Input id="e-code" {...form.register("employee_code")} />
        </Field>
        <Field label="Full name" htmlFor="e-name" error={errors.full_name?.message}>
          <Input id="e-name" {...form.register("full_name")} />
        </Field>
        <Field label="Email (optional)" htmlFor="e-email" error={errors.email?.message}>
          <Input id="e-email" type="email" {...form.register("email")} />
        </Field>
        <Field
          label="Other names"
          htmlFor="e-aliases"
          error={errors.aliases?.message}
          hint="Separate with commas"
        >
          <Input id="e-aliases" {...form.register("aliases")} />
        </Field>
        <Field
          label="First day at the client"
          htmlFor="e-start"
          error={errors.assignment_start?.message}
        >
          <Input id="e-start" type="date" {...form.register("assignment_start")} />
        </Field>
        <Field
          label="Last day"
          htmlFor="e-end"
          error={errors.assignment_end?.message}
          hint="Leave empty if ongoing"
        >
          <Input id="e-end" type="date" {...form.register("assignment_end")} />
        </Field>
      </div>
      {employee ? (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox {...form.register("is_active")} /> Active
        </label>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : employee ? "Save changes" : "Add employee"}
        </Button>
      </div>
    </form>
  );
}
