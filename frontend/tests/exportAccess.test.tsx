// @vitest-environment jsdom
// Who can reach what: reviewers get the payroll export (nav item and page), anonymous
// visitors are sent to /login, and /admin/users still turns reviewers away.
import { isRedirect } from "@tanstack/react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionState, SessionUser } from "../src/api/session";

const session = vi.hoisted(() => ({ state: { status: "anonymous", user: null } as SessionState }));
vi.mock("../src/api/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/api/session")>()),
  ensureSession: async () => session.state,
}));

const { navFor } = await import("../src/components/nav");
const appLayout = await import("../src/routes/_app");
const exportPage = await import("../src/routes/_app/export");
const usersPage = await import("../src/routes/_app/admin.users");

const reviewer: SessionUser = {
  id: "7f3c1c2e-1d4b-4a5e-9f60-1b2c3d4e5f60",
  role: "reviewer",
  name: "Rita Reviewer",
  email: "rita@example.com",
};
const admin: SessionUser = { ...reviewer, role: "admin", name: "Ada Admin" };

type BeforeLoad = (ctx: unknown) => unknown;
const beforeLoadOf = (route: { options: unknown }) =>
  (route.options as { beforeLoad?: BeforeLoad }).beforeLoad;

async function thrown(fn: () => unknown): Promise<unknown> {
  try {
    await fn();
  } catch (e) {
    return e;
  }
  return undefined;
}

const paths = (role: string) => navFor(role).flatMap((s) => s.items.map((i) => i.to));

beforeEach(() => {
  session.state = { status: "anonymous", user: null };
});

describe("navigation", () => {
  it("shows Payroll export to reviewers, but not Users", () => {
    const items = navFor("reviewer").flatMap((s) => s.items);
    expect(items.find((i) => i.to === "/export")?.label).toBe("Payroll export");
    expect(paths("reviewer")).not.toContain("/admin/users");
  });

  it("shows admins everything", () => {
    expect(paths("admin")).toEqual(expect.arrayContaining(["/export", "/admin/users"]));
  });
});

describe("route guards", () => {
  it("sends an anonymous visitor to /login, remembering where they were going", async () => {
    const guard = beforeLoadOf(appLayout.Route);
    const location = {
      href: "/export?week=2026-09-07",
      pathname: "/export",
      searchStr: "?week=2026-09-07",
    };
    const err = await thrown(() => guard?.({ location }));
    expect(isRedirect(err)).toBe(true);
    const options = (err as { options: { to: string; search: { redirect: string } } }).options;
    expect(options.to).toBe("/login");
    expect(options.search.redirect).toBe("/export?week=2026-09-07");
  });

  it("lets a signed-in reviewer open /export (no admin guard on the page)", async () => {
    session.state = { status: "authenticated", user: reviewer };
    const guard = beforeLoadOf(appLayout.Route);
    expect(
      await guard?.({ location: { href: "/export", pathname: "/export", searchStr: "" } }),
    ).toEqual({
      user: reviewer,
    });
    expect(beforeLoadOf(exportPage.Route)).toBeUndefined();
  });

  it("still sends a reviewer away from /admin/users, and lets an admin in", async () => {
    const guard = beforeLoadOf(usersPage.Route);
    expect(guard).toBeDefined();
    const err = await thrown(() => guard?.({ context: { user: reviewer } }));
    expect(isRedirect(err)).toBe(true);
    expect((err as { options: { to: string } }).options.to).toBe("/");
    expect(await thrown(() => guard?.({ context: { user: admin } }))).toBeUndefined();
  });
});
