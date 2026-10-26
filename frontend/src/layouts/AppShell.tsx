import { Link, useMatches } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { CircleUser, LogOut } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { logout } from "@/services/session";
import { useUser } from "@/features/auth";
import { navFor } from "@/layouts/nav";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Styled like the sidebar's nav links. */
const SIDEBAR_ITEM =
  "text-sidebar-foreground/85 hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:outline-none";

export function AppShell({ children }: { children: ReactNode }) {
  const user = useUser();
  const queryClient = useQueryClient();
  // Routes with `staticData: { fullWidth: true }` (the Upload page) own the whole
  // viewport: no width cap, and on desktop a definite height their panels scroll in.
  const fullWidth = useMatches({
    select: (matches) => matches.some((m) => m.staticData?.fullWidth === true),
  });

  // Ending the session makes the _app layout send us to /login. The ref stops a
  // double click from starting a second logout before React re-renders the button.
  const [signingOut, setSigningOut] = useState(false);
  const signingOutRef = useRef(false);
  const onLogout = async () => {
    if (signingOutRef.current) return;
    signingOutRef.current = true;
    setSigningOut(true);
    try {
      await logout();
      queryClient.clear();
    } finally {
      signingOutRef.current = false;
      setSigningOut(false);
    }
  };

  // Admin-only items (Users) are filtered out for reviewers in navFor.
  const sections = navFor(user.role);

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
                      className={cn(
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors data-[status=active]:bg-sidebar-accent data-[status=active]:font-medium data-[status=active]:text-white",
                        SIDEBAR_ITEM,
                      )}
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
            title={user.email}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent data-[status=active]:bg-sidebar-accent"
          >
            <CircleUser className="size-4" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{user.name}</span>
            <span className="text-[11px] text-sidebar-muted capitalize">{user.role}</span>
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn("mt-1 w-full justify-start px-2", SIDEBAR_ITEM)}
            disabled={signingOut}
            onClick={() => void onLogout()}
          >
            <LogOut /> Sign out
          </Button>
        </div>
      </aside>

      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col",
          fullWidth && "md:h-dvh md:min-h-0 md:overflow-hidden",
        )}
      >
        {/* Small screens only: the sidebar is hidden there, so the title, a compact nav
            and Sign out live here. On md and up the sidebar has all of it. */}
        <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur md:hidden">
          <div className="flex h-14 items-center justify-between gap-3 px-4">
            <span className="text-sm font-semibold">Timesheet Assistant</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              disabled={signingOut}
              onClick={() => void onLogout()}
            >
              <LogOut />
            </Button>
          </div>
          <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-2">
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
        <main
          id="main"
          data-layout={fullWidth ? "full" : "capped"}
          className={cn(
            "w-full flex-1",
            fullWidth
              ? // Between md and lg the page stacks into one column: it scrolls here.
                "flex max-w-none min-h-0 flex-col px-4 py-4 md:overflow-y-auto md:px-6 lg:overflow-hidden"
              : "mx-auto max-w-[1400px] px-4 py-6 md:px-6",
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
