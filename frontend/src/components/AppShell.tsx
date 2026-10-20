import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CalendarDays,
  ClipboardCheck,
  FileSpreadsheet,
  Inbox,
  LayoutDashboard,
  LogOut,
  Upload,
  UserCog,
  Users,
  CircleUser,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { logout } from "@/api/session";
import { useUser } from "@/auth/useSession";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type NavItem = {
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

const NAV: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Work",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
      { to: "/review", label: "Review queue", icon: ClipboardCheck },
      { to: "/submissions", label: "Submissions", icon: Inbox },
      { to: "/upload", label: "Upload", icon: Upload },
      { to: "/export", label: "Payroll export", icon: FileSpreadsheet, adminOnly: true },
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

export function AppShell({ children }: { children: ReactNode }) {
  const user = useUser();
  const isAdmin = user.role === "admin";
  const queryClient = useQueryClient();

  // Ending the session makes the _app layout send us to /login.
  const onLogout = async () => {
    await logout();
    queryClient.clear();
  };

  const sections = NAV.map((s) => ({
    ...s,
    items: s.items.filter((i) => !i.adminOnly || isAdmin),
  }));

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-card px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>

      {/* Sidebar (md and up) */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
        <div className="flex h-14 items-center gap-2 px-5">
          <span className="grid size-7 place-items-center rounded-md bg-white/10 text-sm font-bold">
            T
          </span>
          <span className="text-sm font-semibold tracking-tight">Timesheet Assistant</span>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
          {sections.map((section) => (
            <div key={section.heading}>
              <p className="px-2 pb-1 text-[11px] font-medium tracking-wider text-sidebar-muted uppercase">
                {section.heading}
              </p>
              <ul className="space-y-0.5">
                {section.items.map((item) => (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      activeOptions={{ exact: item.exact ?? false }}
                      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/85 transition-colors hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:outline-none data-[status=active]:bg-sidebar-accent data-[status=active]:font-medium data-[status=active]:text-white"
                    >
                      <item.icon className="size-4" aria-hidden />
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 p-3">
          <Link
            to="/account"
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent data-[status=active]:bg-sidebar-accent"
          >
            <CircleUser className="size-4" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{user.name}</span>
            <span className="text-[11px] text-sidebar-muted capitalize">{user.role}</span>
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur">
          <div className="flex h-14 items-center justify-between gap-3 px-4 md:px-6">
            <span className="text-sm font-semibold md:hidden">Timesheet Assistant</span>
            <span className="hidden text-sm text-muted-foreground md:block">{user.email}</span>
            <div className="flex items-center gap-2">
              <Badge variant={isAdmin ? "default" : "secondary"} className="capitalize">
                {user.role}
              </Badge>
              <Button variant="ghost" size="sm" onClick={() => void onLogout()}>
                <LogOut /> Sign out
              </Button>
            </div>
          </div>
          {/* Compact nav for small screens */}
          <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-2 md:hidden">
            {sections
              .flatMap((s) => s.items)
              .concat([{ to: "/account", label: "Account", icon: CircleUser }])
              .map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  activeOptions={{ exact: item.exact ?? false }}
                  className={cn(
                    "shrink-0 rounded-md px-2.5 py-1 text-sm text-muted-foreground",
                    "data-[status=active]:bg-primary/10 data-[status=active]:font-medium data-[status=active]:text-primary",
                  )}
                >
                  {item.label}
                </Link>
              ))}
          </nav>
        </header>
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}
