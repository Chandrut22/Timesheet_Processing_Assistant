// The companies a holiday is for: a checkbox list of the active companies, with
// "Select all" and "Clear". Used to add one holiday to several companies, and as the
// targets of "Copy holidays".
import { useMemo, type JSX } from "react";
import { useCompanyMap } from "@/features/companies";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/input";

export function CompanyChecklist({
  id,
  value,
  onChange,
  exclude,
  error,
  label = "Companies",
}: {
  id: string;
  value: string[];
  onChange: (ids: string[]) => void;
  /** Left out of the list (the company being copied from). */
  exclude?: string;
  error?: string;
  label?: string;
}): JSX.Element {
  const map = useCompanyMap();
  const companies = useMemo(
    () =>
      [...map.values()]
        .filter((c) => c.is_active && c.id !== exclude)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [map, exclude],
  );
  const chosen = new Set(value);
  const toggle = (companyId: string): void =>
    onChange(chosen.has(companyId) ? value.filter((v) => v !== companyId) : [...value, companyId]);

  return (
    <fieldset className="grid gap-1.5" aria-describedby={error ? `${id}-error` : undefined}>
      <div className="flex items-center justify-between gap-2">
        <legend className="text-sm font-medium">{label}</legend>
        <span className="flex gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => onChange(companies.map((c) => c.id))}
            disabled={companies.length === 0}
          >
            Select all
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => onChange([])}
            disabled={value.length === 0}
          >
            Clear
          </Button>
        </span>
      </div>
      {companies.length === 0 ? (
        <p className="text-sm text-muted-foreground">No active companies.</p>
      ) : (
        <ul className="grid max-h-56 gap-1 overflow-y-auto rounded-md border p-2">
          {companies.map((c) => (
            <li key={c.id}>
              <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-accent">
                <Checkbox checked={chosen.has(c.id)} onChange={() => toggle(c.id)} />
                <span className="truncate">{c.name}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        {value.length === 0
          ? "Each holiday belongs to one company: choose at least one."
          : `${value.length} selected`}
      </p>
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
