// @vitest-environment jsdom
// A timesheet whose sheet gave only a weekly total: what the reviewer sees and the week change.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "./fixtures/api-responses.json";
import type { TimesheetRead } from "../src/api/models";

const setWeek = vi.hoisted(() => vi.fn());
vi.mock("../src/api/core", () => ({ coreApi: { setWeek } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { WeeklyTotalPanel } = await import("../src/features/timesheet/WeeklyTotalPanel");
const { isWeeklyTotal } = await import("../src/lib/severity");

const flag = (code: string) => ({ code, message: code, severity: "medium" });
const weeklyTotal = (over: Partial<TimesheetRead> = {}): TimesheetRead => ({
  ...(fixtures.core.timesheet as TimesheetRead),
  entries: [],
  stated_total: 42,
  regular_hours: 40,
  overtime_hours: 2,
  week_start: "2026-10-12",
  flags: [flag("weekly_total_only"), flag("week_assumed")],
  ...over,
});

function renderPanel(t: TimesheetRead, readOnly = false) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <WeeklyTotalPanel t={t} weekStartDay={0} readOnly={readOnly} />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

beforeEach(() => setWeek.mockReset());
afterEach(cleanup);

describe("WeeklyTotalPanel", () => {
  it("is used only for a weekly total with no days", () => {
    expect(isWeeklyTotal(weeklyTotal())).toBe(true);
    expect(isWeeklyTotal(weeklyTotal({ flags: [] }))).toBe(false);
    const withDays = weeklyTotal({ entries: (fixtures.core.timesheet as TimesheetRead).entries });
    expect(withDays.entries.length > 0 && isWeeklyTotal(withDays)).toBe(false);
  });

  it("explains the total, the overtime split and the assumed week", () => {
    renderPanel(weeklyTotal());
    expect(screen.getByText(/42(\.00)? h/)).toBeTruthy();
    expect(screen.getByText(/2(\.00)? h overtime/)).toBeTruthy();
    expect(screen.getByText(/the week is assumed/)).toBeTruthy();
  });

  it("moves it to another week, and refuses a day that does not start a week", async () => {
    setWeek.mockResolvedValue(
      weeklyTotal({ week_start: "2026-10-05", flags: [flag("weekly_total_only")] }),
    );
    const user = renderPanel(weeklyTotal());
    const input = screen.getByLabelText("Week starting");
    const button = screen.getByRole("button", { name: "Change week" });
    expect(button.hasAttribute("disabled")).toBe(true); // nothing changed yet

    fireEvent.change(input, { target: { value: "2026-10-07" } }); // a Wednesday
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/pick a Monday/)).toBeTruthy();

    fireEvent.change(input, { target: { value: "2026-10-05" } });
    await user.click(button);
    expect(setWeek).toHaveBeenCalledWith(weeklyTotal().id, "2026-10-05");
  });

  it("shows the week without controls when read-only", () => {
    renderPanel(weeklyTotal({ status: "exported" }), true);
    expect(screen.queryByRole("button", { name: "Change week" })).toBeNull();
    expect(screen.queryByLabelText("Week starting")).toBeNull();
  });
});
