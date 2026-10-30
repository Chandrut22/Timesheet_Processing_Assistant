// @vitest-environment jsdom
// Creating a payroll sheet marks its timesheets exported, so both lists refresh.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { clientWrapper, testQueryClient } from "@/test/render";

const api = vi.hoisted(() => ({ createExport: vi.fn(), downloadExport: vi.fn() }));
vi.mock("../services/exportService", () => ({ exportService: api }));
vi.mock("@/features/timesheets", () => ({ timesheetKeys: { all: ["timesheets"] } }));

const { useCreateExport } = await import("./useExportActions");

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("sends the company, week and allow-pending, then refreshes exports and timesheets", async () => {
  const batch = { id: "b1", row_count: 3 };
  api.createExport.mockResolvedValue(batch);
  const client = testQueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const onSuccess = vi.fn();
  const { result } = renderHook(() => useCreateExport("c1", "2026-10-12", { onSuccess }), {
    wrapper: clientWrapper(client),
  });

  await act(() => result.current.mutateAsync(true));

  expect(api.createExport).toHaveBeenCalledWith("c1", "2026-10-12", true);
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["exports"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["timesheets"] });
  expect(onSuccess).toHaveBeenCalledWith(batch, true);
});
