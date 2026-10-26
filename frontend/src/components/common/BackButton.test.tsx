// @vitest-environment jsdom
// Back goes back in the browser history when there is an earlier page in this tab, and
// to the fallback page when the page was opened directly.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({
  canGoBack: false,
  back: vi.fn(),
  linkNavigations: [] as string[],
}));

vi.mock("@tanstack/react-router", () => ({
  useCanGoBack: () => router.canGoBack,
  useRouter: () => ({ history: { back: router.back } }),
  // Like TanStack's Link: our onClick runs first; it navigates unless that prevented it.
  Link: ({
    to,
    onClick,
    children,
    className,
  }: {
    to: string;
    onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
    children: ReactNode;
    className?: string;
  }) => (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        onClick?.(e);
        const navigates = !e.defaultPrevented && e.button === 0 && !e.ctrlKey && !e.metaKey;
        e.preventDefault(); // jsdom can't follow links
        if (navigates) router.linkNavigations.push(to);
      }}
    >
      {children}
    </a>
  ),
}));

const { BackButton } = await import("./BackButton");

beforeEach(() => {
  router.back.mockReset();
  router.linkNavigations = [];
});
afterEach(cleanup);

describe("BackButton", () => {
  it("goes back in the history when there is an earlier page", () => {
    router.canGoBack = true;
    render(<BackButton fallback="/review" fallbackLabel="Review queue" />);
    const link = screen.getByRole("link", { name: "Back" });
    fireEvent.click(link);
    expect(router.back).toHaveBeenCalledTimes(1);
    expect(router.linkNavigations).toEqual([]); // no new history entry
  });

  it("opens the fallback page when the page was opened directly", () => {
    router.canGoBack = false;
    render(<BackButton fallback="/submissions" fallbackLabel="Submissions" />);
    const link = screen.getByRole("link", { name: "Submissions" });
    expect(link.getAttribute("href")).toBe("/submissions");
    fireEvent.click(link);
    expect(router.back).not.toHaveBeenCalled();
    expect(router.linkNavigations).toEqual(["/submissions"]);
  });

  it("Ctrl-click leaves the history alone (the browser opens the link in a new tab)", () => {
    router.canGoBack = true;
    render(<BackButton fallback="/" fallbackLabel="Dashboard" />);
    fireEvent.click(screen.getByRole("link", { name: "Back" }), { ctrlKey: true });
    expect(router.back).not.toHaveBeenCalled();
  });
});
