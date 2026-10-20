import type { FlagRead } from "@/api/models";

export type Severity = "high" | "medium" | "low";
const RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

export function sortFlags(flags: FlagRead[]): FlagRead[] {
  return [...flags].sort((a, b) => (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3));
}

export function groupFlags(flags: FlagRead[]): Record<Severity, FlagRead[]> {
  const out: Record<Severity, FlagRead[]> = { high: [], medium: [], low: [] };
  for (const f of flags) {
    const key = (f.severity in out ? f.severity : "low") as Severity;
    out[key].push(f);
  }
  return out;
}

export function hasFlag(flags: FlagRead[], ...codes: string[]): boolean {
  return flags.some((f) => codes.includes(f.code));
}

/** Pulls employee candidates from a flag's extra keys, whatever shape they arrive in. */
export function flagCandidates(flags: FlagRead[]): { id: string; label: string | null }[] {
  const out = new Map<string, string | null>();
  for (const f of flags) {
    const raw = f["candidates"];
    if (!Array.isArray(raw)) continue;
    for (const c of raw) {
      if (typeof c === "string") out.set(c, out.get(c) ?? null);
      else if (c && typeof c === "object") {
        const obj = c as Record<string, unknown>;
        const id = obj["employee_id"] ?? obj["id"];
        if (typeof id !== "string") continue;
        const name = obj["full_name"] ?? obj["name"];
        const code = obj["employee_code"] ?? obj["code"];
        const label =
          [typeof name === "string" ? name : null, typeof code === "string" ? `(${code})` : null]
            .filter(Boolean)
            .join(" ") || null;
        out.set(id, label ?? out.get(id) ?? null);
      }
    }
  }
  return [...out.entries()].map(([id, label]) => ({ id, label }));
}

export function otherTimesheetId(flag: FlagRead): string | null {
  const v = flag["other_timesheet_id"];
  return typeof v === "string" ? v : null;
}
