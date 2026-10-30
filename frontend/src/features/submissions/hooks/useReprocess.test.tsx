// @vitest-environment jsdom
// Reprocess: the variables reach the API in order, both lists refresh, and a 409
// confirmation_required reaches the dialog (which offers to send it again, confirmed).
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clientWrapper, testQueryClient } from "@/test/render";
import { ApiError } from "@/utils/errors";

const api = vi.hoisted(() => ({ reprocess: vi.fn() }));
vi.mock("../services/submissionService", () => ({ submissionService: api }));
vi.mock("@/features/timesheets", () => ({ timesheetKeys: { all: ["timesheets"] } }));

const { useReprocess } = await import("./useReprocess");

const VARS = { reason: "Wrong week", documentId: "d1", confirmApproved: false, refetch: true };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useReprocess", () => {
  it("queues the run and refreshes submissions and timesheets", async () => {
    api.reprocess.mockResolvedValue({ id: "r1" });
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useReprocess("s1"), { wrapper: clientWrapper(client) });

    await act(() => result.current.mutateAsync(VARS));

    expect(api.reprocess).toHaveBeenCalledWith("s1", "Wrong week", "d1", false, true);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["submissions"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["timesheets"] });
  });

  it("hands a 409 to the dialog and refreshes nothing", async () => {
    const conflict = new ApiError({
      status: 409,
      message: "2 timesheets are approved.",
      code: "confirmation_required",
    });
    api.reprocess.mockRejectedValue(conflict);
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const onError = vi.fn();
    const { result } = renderHook(() => useReprocess("s1", { onError }), {
      wrapper: clientWrapper(client),
    });

    await act(async () => {
      await expect(result.current.mutateAsync(VARS)).rejects.toBe(conflict);
    });

    expect(onError).toHaveBeenCalledWith(conflict, VARS);
    expect(invalidate).not.toHaveBeenCalled();
  });
});
