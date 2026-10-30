// @vitest-environment jsdom
// Company hooks own the cache work: the saved company replaces the cached one and the
// lists refresh; the screen only adds its toast.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clientWrapper, testQueryClient } from "@/test/render";

const api = vi.hoisted(() => ({
  updateCompany: vi.fn(),
  addWhitelist: vi.fn(),
  bulkCompanyStatus: vi.fn(),
}));
vi.mock("../services/companyService", () => ({ companyService: api }));
vi.mock("@/features/employees", () => ({ employeeKeys: { all: ["employees"] } }));

const { companyBulkStatus, useAddWhitelist, useUpdateCompany } =
  await import("./useCompanyMutations");

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useUpdateCompany", () => {
  it("puts the saved company in the cache, refreshes the lists, then calls the screen", async () => {
    const saved = { id: "c1", name: "Lakeside" };
    api.updateCompany.mockResolvedValue(saved);
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useUpdateCompany("c1", { onSuccess }), {
      wrapper: clientWrapper(client),
    });

    await act(() => result.current.mutateAsync({ name: "Lakeside" }));

    expect(api.updateCompany).toHaveBeenCalledWith("c1", { name: "Lakeside" });
    expect(client.getQueryData(["companies", "detail", "c1"])).toEqual(saved);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["companies"] });
    expect(onSuccess).toHaveBeenCalledWith(saved, { name: "Lakeside" });
  });
});

describe("useAddWhitelist", () => {
  it("refreshes only that company's senders", async () => {
    api.addWhitelist.mockResolvedValue({ id: "w1", value: "acme.com" });
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useAddWhitelist("c1"), {
      wrapper: clientWrapper(client),
    });

    await act(() => result.current.mutateAsync("acme.com"));

    expect(api.addWhitelist).toHaveBeenCalledWith("c1", "acme.com");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["companies", "whitelist", "c1"] });
  });
});

it("bulk status refreshes companies and employees (deactivating cascades)", () => {
  expect(companyBulkStatus.invalidate).toEqual([["companies"], ["employees"]]);
  expect(companyBulkStatus.setStatus).toBe(api.bulkCompanyStatus);
});
