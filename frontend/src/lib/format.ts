// Formatting helpers. Pure functions (no React), unit-tested in tests/format.test.ts.
import { addDays, format, formatDistanceToNow, isValid, parseISO } from "date-fns";

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const d = typeof value === "string" ? parseISO(value) : value;
  return isValid(d) ? d : null;
}

/** 1234.5, 'INR' -> '₹1,234.50'. Null stays null so callers can show "rate missing". */
export function formatMoney(
  amount: number | null | undefined,
  currency?: string | null,
): string | null {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return null;
  const cur = currency && /^[A-Z]{3}$/.test(currency) ? currency : undefined;
  try {
    return new Intl.NumberFormat("en-IN", {
      style: cur ? "currency" : "decimal",
      currency: cur,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return amount.toFixed(2);
  }
}

/** 8 -> '8', 7.5 -> '7.5', 7.25 -> '7.25'. */
export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return "—";
  return String(Math.round(hours * 100) / 100);
}

/** 0.873 -> '87%'. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatDate(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? format(d, "d MMM yyyy") : "—";
}

export function formatDateTime(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? format(d, "d MMM yyyy, HH:mm") : "—";
}

export function formatTime(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? format(d, "HH:mm") : "—";
}

export function formatRelative(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? formatDistanceToNow(d, { addSuffix: true }) : "—";
}

/** '2026-10-12' -> '12–18 Oct 2026' (a 7-day week starting that day). */
export function formatWeek(weekStart: string | null | undefined): string {
  const start = toDate(weekStart);
  if (!start) return "—";
  const end = addDays(start, 6);
  if (start.getFullYear() !== end.getFullYear())
    return `${format(start, "d MMM yyyy")} – ${format(end, "d MMM yyyy")}`;
  if (start.getMonth() !== end.getMonth())
    return `${format(start, "d MMM")} – ${format(end, "d MMM yyyy")}`;
  return `${format(start, "d")}–${format(end, "d MMM yyyy")}`;
}

export function formatDayLabel(value: string | null | undefined): string {
  const d = toDate(value);
  return d ? format(d, "EEE d MMM") : "—";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** 'needs_review' -> 'Needs review'. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** ISO date (yyyy-MM-dd) for a Date, in local time. */
export function toIsoDate(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** Backend weekday (0 = Monday … 6 = Sunday) of an ISO date. */
export function backendWeekday(isoDate: string): number | null {
  const d = toDate(isoDate);
  return d ? (d.getDay() + 6) % 7 : null;
}

/** The most recent date on or before `from` that falls on backend weekday `weekStart`. */
export function latestWeekStart(weekStart: number, from: Date = new Date()): string {
  const current = (from.getDay() + 6) % 7;
  const back = (current - weekStart + 7) % 7;
  return toIsoDate(addDays(from, -back));
}

export function shiftIsoDate(isoDate: string, days: number): string {
  const d = toDate(isoDate);
  return d ? toIsoDate(addDays(d, days)) : isoDate;
}

/** Number of whole days from a to b (b - a). */
export function daysBetween(a: string, b: string): number | null {
  const da = toDate(a);
  const db = toDate(b);
  if (!da || !db) return null;
  return Math.round((db.getTime() - da.getTime()) / 86_400_000);
}

export function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
