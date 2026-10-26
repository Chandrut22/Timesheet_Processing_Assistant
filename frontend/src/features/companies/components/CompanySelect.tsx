import type * as React from "react";
import { NativeSelect } from "@/components/ui/input";
import { useCompanies } from "../hooks/useCompanies";

/** A company <select> fed by the cached company list. */
export function CompanySelect({
  value,
  onChange,
  allLabel = "All companies",
  includeAll = true,
  activeOnly = false,
  ...props
}: Omit<React.ComponentProps<"select">, "value" | "onChange"> & {
  value: string;
  onChange: (id: string) => void;
  allLabel?: string;
  includeAll?: boolean;
  activeOnly?: boolean;
}) {
  const { data, isLoading } = useCompanies();
  const companies = (data ?? []).filter((c) => !activeOnly || c.is_active);
  return (
    <NativeSelect
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={isLoading}
      {...props}
    >
      {includeAll ? (
        <option value="">{isLoading ? "Loading…" : allLabel}</option>
      ) : (
        <option value="" disabled>
          {isLoading ? "Loading…" : "Choose a company…"}
        </option>
      )}
      {companies.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
          {c.is_active ? "" : " (inactive)"}
        </option>
      ))}
    </NativeSelect>
  );
}
