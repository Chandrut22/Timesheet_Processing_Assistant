// @vitest-environment jsdom
// The layout: Sign out lives under the user's name in the sidebar (and as an icon in the
// mobile header); the desktop top bar is gone; full-width routes get the full-height layout.
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  matches: [] as { staticData?: { fullWidth?: boolean } }[],
  logout: vi.fn<() => Promise<void>>(),
}));

vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  Link: (props: { to: string; children: ReactNode; title?: string; className?: string }) => (
    <a href={props.to} title={props.title} className={props.className}>
      {props.children}
    </a>
  ),
  useMatches: ({ select }: { select: (m: typeof state.matches) => unknown }) =>
    select(state.matches),
}));
vi.mock("@/features/auth/hooks/useSession", () => ({
  useUser: () => ({
    id: "u1",
    role: "reviewer",
    name: "Rita Reviewer",
    email: "rita@example.com",
  }),
}));
vi.mock("@/services/session", () => ({ logout: state.logout }));

const { AppShell } = await import("./AppShell");

function renderShell() {
  const client = new QueryClient();
  const clear = vi.spyOn(client, "clear");
  render(
    <QueryClientProvider client={client}>
      <AppShell>
        <p>Page content</p>
      </AppShell>
    </QueryClientProvider>,
  );
  return { clear, user: userEvent.setup() };
}

beforeEach(() => {
  state.matches = [];
  state.logout.mockReset();
  state.logout.mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("AppShell", () => {
  it("shows the name, role and a Sign out button in the sidebar footer", () => {
    renderShell();
    const sidebar = screen.getByRole("complementary");
    expect(within(sidebar).getByText("Rita Reviewer")).toBeTruthy();
    expect(within(sidebar).getByText("reviewer")).toBeTruthy();
    const button = within(sidebar).getByRole("button", { name: "Sign out" });
    expect(button.getAttribute("type")).toBe("button");
    // The email is only a tooltip on the account link now.
    expect(
      within(sidebar)
        .getByRole("link", { name: /Rita Reviewer/ })
        .getAttribute("title"),
    ).toBe("rita@example.com");
  });

  it("signs out once and clears the query cache", async () => {
    const { clear, user } = renderShell();
    await user.click(
      within(screen.getByRole("complementary")).getByRole("button", { name: "Sign out" }),
    );
    expect(state.logout).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledTimes(1);
  });

  it("ignores a double click while signing out", async () => {
    let finish: () => void = () => undefined;
    state.logout.mockImplementation(() => new Promise<void>((resolve) => (finish = resolve)));
    const { user } = renderShell();
    const button = within(screen.getByRole("complementary")).getByRole("button", {
      name: "Sign out",
    });
    await user.dblClick(button);
    expect(state.logout).toHaveBeenCalledTimes(1);
    expect(button.hasAttribute("disabled")).toBe(true);
    finish();
  });

  it("has no desktop top bar: the header is mobile-only, with no email or role badge", () => {
    renderShell();
    const header = screen.getByRole("banner");
    expect(header.className.split(" ")).toContain("md:hidden");
    expect(screen.queryByText("rita@example.com")).toBeNull();
    expect(within(header).queryByText("reviewer")).toBeNull();
    // The one button in it is the mobile Sign out (icon only, named by aria-label).
    const buttons = within(header).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0].getAttribute("aria-label")).toBe("Sign out");
  });

  it("keeps a Sign out button in the mobile header", async () => {
    const { user } = renderShell();
    await user.click(within(screen.getByRole("banner")).getByRole("button", { name: "Sign out" }));
    expect(state.logout).toHaveBeenCalledTimes(1);
  });

  it("gives full-width routes the full-height layout, and caps the others", () => {
    renderShell();
    let main = screen.getByRole("main");
    expect(main.dataset.layout).toBe("capped");
    expect(main.className).toContain("max-w-[1400px]");
    cleanup();

    state.matches = [{ staticData: {} }, { staticData: { fullWidth: true } }];
    renderShell();
    main = screen.getByRole("main");
    expect(main.dataset.layout).toBe("full");
    expect(main.className).toContain("max-w-none");
    expect(main.className).not.toContain("max-w-[1400px]");
    expect(main.parentElement?.className).toContain("md:h-dvh");
  });
});
