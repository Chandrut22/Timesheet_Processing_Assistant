// The shared frame of the public pages (login, forgot / reset password): the decorative
// background, the product name and the card the page sits in.
import { Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { AuthBackground } from "@/layouts/AuthBackground";

/** The background alone: shown while the session check runs (no blank page). */
export function AuthPending() {
  return (
    <div className="relative isolate min-h-dvh overflow-hidden">
      <AuthBackground />
    </div>
  );
}

export function AuthLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="relative isolate grid min-h-dvh place-items-center overflow-hidden px-4 py-10">
      <AuthBackground />
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid size-8 place-items-center rounded-md bg-sidebar text-sm font-bold text-white">
            T
          </span>
          <span className="text-base font-semibold tracking-tight">Timesheet Assistant</span>
        </div>
        <div className="auth-card rounded-lg border bg-card/90 p-6 shadow-lg ring-1 ring-foreground/5 backdrop-blur-sm">
          {children ?? <Outlet />}
        </div>
      </div>
    </div>
  );
}
