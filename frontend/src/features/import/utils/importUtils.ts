// Pure helpers for the import dialog (unit-tested in importUtils.test.ts).
import type {
  ImportReport,
  ImportResource,
  OnDuplicate,
  OnError,
  RowResult,
} from "../types/import";

export const RESOURCE_LABEL: Record<ImportResource, { one: string; many: string }> = {
  users: { one: "user", many: "users" },
  employees: { one: "employee", many: "employees" },
  companies: { one: "company", many: "companies" },
  holidays: { one: "holiday", many: "holidays" },
};

/** What makes two rows "the same record", in the words of each import. */
export const NATURAL_KEY: Record<ImportResource, string> = {
  users: "the same email",
  employees: "the same employee code in the same company",
  companies: "the same name",
  holidays: "the same date for the same company",
};

export const ON_ERROR_OPTIONS: { value: OnError; label: string }[] = [
  { value: "abort", label: "Import nothing if any row has a problem" },
  { value: "skip", label: "Import the good rows, skip the rest" },
];

export function onDuplicateOptions(
  resource: ImportResource,
): { value: OnDuplicate; label: string }[] {
  const options: { value: OnDuplicate; label: string }[] = [
    { value: "error", label: "Report it as a problem" },
    { value: "skip", label: "Skip it" },
  ];
  // Changing a user's role or status has its own rules: one person at a time, on the Users screen.
  if (resource !== "users")
    options.push({ value: "update", label: "Update it with the file's values" });
  return options;
}

const count = (n: number, one: string, many: string): string =>
  `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** One sentence for the result: "Would create 3 employees, skip 1. 2 rows have problems." */
export function summarize(report: ImportReport, resource: ImportResource): string {
  const { one, many } = RESOURCE_LABEL[resource];
  const verb = report.committed
    ? ["Created", "updated", "skipped"]
    : ["Would create", "update", "skip"];
  const parts = [`${verb[0]} ${count(report.created, one, many)}`];
  if (report.updated) parts.push(`${verb[1]} ${report.updated.toLocaleString()}`);
  if (report.skipped) parts.push(`${verb[2]} ${report.skipped.toLocaleString()}`);
  let text = `${parts.join(", ")}.`;
  if (report.failed) text += ` ${count(report.failed, "row has", "rows have")} problems.`;
  if (!report.dry_run && !report.committed)
    text = `Nothing was imported: ${count(report.failed, "row has", "rows have")} problems.`;
  return text;
}

/** After a check: can the same file be imported with the same options? */
export function canCommit(report: ImportReport | null): boolean {
  if (!report || !report.dry_run) return false;
  if (report.created + report.updated === 0) return false;
  return report.on_error === "skip" || report.failed === 0;
}

/** "email: value is not a valid email address; Same email as row 3." */
export function rowProblems(row: RowResult): string {
  return row.errors.map((e) => (e.column ? `${e.column}: ${e.message}` : e.message)).join("; ");
}

export const STATUS_BADGE = {
  created: "success",
  updated: "info",
  skipped: "muted",
  failed: "danger",
} as const satisfies Record<RowResult["status"], string>;
