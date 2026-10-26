// @vitest-environment jsdom
// The sign-in frame: shows its page, keeps the background out of the accessibility tree,
// and leaves the login form fully usable.
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  Outlet: () => <p>Outlet content</p>,
  Link: (props: { to: string; children: ReactNode; className?: string }) => (
    <a href={props.to} className={props.className}>
      {props.children}
    </a>
  ),
  useRouter: () => ({ history: { push: () => undefined } }),
  redirect: (options: unknown) => options,
  getRouteApi: () => ({ useSearch: () => ({}) }),
}));

const { AuthLayout, AuthPending } = await import("./AuthLayout");
const { AuthBackground } = await import("./AuthBackground");
const { LoginPage } = await import("@/features/auth/components/LoginPage");

afterEach(cleanup);

describe("AuthLayout", () => {
  it("shows the page it is given", () => {
    render(
      <AuthLayout>
        <p>Child page</p>
      </AuthLayout>,
    );
    expect(screen.getByText("Child page")).toBeTruthy();
    expect(screen.getByText("Timesheet Assistant")).toBeTruthy();
  });

  it("shows the route's Outlet when given no child", () => {
    render(<AuthLayout />);
    expect(screen.getByText("Outlet content")).toBeTruthy();
  });

  it("shows only the background while the session check runs", () => {
    render(<AuthPending />);
    expect(screen.getByTestId("auth-background")).toBeTruthy();
    expect(screen.queryByText("Outlet content")).toBeNull();
  });
});

describe("AuthBackground", () => {
  it("is decorative: hidden from assistive technology, nothing to click or focus", () => {
    render(<AuthBackground />);
    const root = screen.getByTestId("auth-background");
    expect(root.getAttribute("aria-hidden")).toBe("true");
    expect(root.className).toContain("pointer-events-none");
    expect(root.querySelectorAll("a, button, input, select, textarea, [tabindex]")).toHaveLength(0);
  });
});

describe("login form on the new background", () => {
  it("keeps its labels, fields and Sign in button reachable by role", () => {
    render(
      <AuthLayout>
        <LoginPage />
      </AuthLayout>,
    );
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Email" })).toBeTruthy();
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
    // The decorative layer adds nothing to the accessible page.
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });
});
