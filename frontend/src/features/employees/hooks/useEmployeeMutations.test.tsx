// @vitest-environment jsdom
// One hook saves a new or an existing employee: id null creates, an id updates.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clientWrapper, testQueryClient } from "@/test/render";

const api = vi.hoisted(() => ({
  createEmployee: vi.fn(),
  updateEmployee: vi.fn(),
  bulkEmployeeStatus: vi.fn(),
}));
vi.mock("../services/employeeService", () => ({ employeeService: api }));

const { useSaveEmployee } = await import("./useEmployeeMutations");

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useSaveEmployee", () => {
  it("creates when there is no id", async () => {
    api.createEmployee.mockResolvedValue({ id: "e1", full_name: "Grace Hopper" });
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useSaveEmployee(), { wrapper: clientWrapper(client) });
    const body = { company_id: "c1", employee_code: "E1", full_name: "Grace Hopper" };

    await act(() => result.current.mutateAsync({ id: null, body }));

    expect(api.createEmployee).toHaveBeenCalledWith(body);
    expect(api.updateEmployee).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["employees"] });
  });

  it("updates when there is an id", async () => {
    api.updateEmployee.mockResolvedValue({ id: "e1", full_name: "Grace Hopper" });
    const { result } = renderHook(() => useSaveEmployee(), {
      wrapper: clientWrapper(testQueryClient()),
    });

    await act(() => result.current.mutateAsync({ id: "e1", body: { full_name: "Grace" } }));

    expect(api.updateEmployee).toHaveBeenCalledWith("e1", { full_name: "Grace" });
    expect(api.createEmployee).not.toHaveBeenCalled();
  });
});
