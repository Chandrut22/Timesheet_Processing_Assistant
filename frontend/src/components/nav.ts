// The sidebar's sections, and which role sees which item. Kept out of AppShell.tsx so
// the role rules are unit-tested (tests/exportAccess.test.ts). Hiding an item is only
// for tidiness: admin pages also redirect reviewers (requireAdmin) and the API refuses
// them (403).
import {
  Building2,
  CalendarDays,
  ClipboardCheck,
  FileSpreadsheet,
  Inbox,
  LayoutDashboard,
  Upload,
  UserCog,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { RoleName } from "@/api/models";

export type NavItem = {
  to:
    | "/"
    | "/review"
    | "/submissions"
    | "/upload"
    | "/export"
    | "/companies"
    | "/employees"
    | "/holidays"
    | "/admin/users"
    | "/account";
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
  exact?: boolean;
};

export const NAV: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Work",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
      { to: "/review", label: "Review queue", icon: ClipboardCheck },
      { to: "/submissions", label: "Submissions", icon: Inbox },
      { to: "/upload", label: "Upload", icon: Upload },
      // Reviewers export payroll too (CSV or Excel).
      { to: "/export", label: "Payroll export", icon: FileSpreadsheet },
    ],
  },
  {
    heading: "Setup",
    items: [
      { to: "/companies", label: "Companies", icon: Building2 },
      { to: "/employees", label: "Employees", icon: Users },
      { to: "/holidays", label: "Holidays", icon: CalendarDays },
      { to: "/admin/users", label: "Users", icon: UserCog, adminOnly: true },
    ],
  },
];

/** The sections a user with this role sees (admin-only items removed for reviewers). */
export function navFor(role: RoleName | string): { heading: string; items: NavItem[] }[] {
  return NAV.map((s) => ({
    ...s,
    items: s.items.filter((i) => !i.adminOnly || role === "admin"),
  }));
}
