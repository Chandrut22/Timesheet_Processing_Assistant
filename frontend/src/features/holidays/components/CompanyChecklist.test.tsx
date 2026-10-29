// @vitest-environment jsdom
// The company checkboxes on the Holidays page: active companies only, Select all / Clear,
// and the company being copied from is left out.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyChecklist } from "./CompanyChecklist";

vi.mock("@/features/companies", () => ({
  useCompanyMap: () =>
    new Map([
      ["b", { id: "b", name: "Hillview", is_active: true }],
      ["a", { id: "a", name: "Lakeside", is_active: true }],
      ["z", { id: "z", name: "Closed Co", is_active: false }],
    ]),
}));

afterEach(cleanup);

describe("CompanyChecklist", () => {
  it("lists active companies by name and toggles one", () => {
    const onChange = vi.fn();
    render(<CompanyChecklist id="c" value={["a"]} onChange={onChange} />);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes.map((b) => b.closest("label")?.textContent)).toEqual(["Hillview", "Lakeside"]);
    expect((boxes[1] as HTMLInputElement).checked).toBe(true);
    fireEvent.click(boxes[0]);
    expect(onChange).toHaveBeenLastCalledWith(["a", "b"]);
    fireEvent.click(boxes[1]);
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("selects all, clears, and leaves out the source company", () => {
    const onChange = vi.fn();
    render(<CompanyChecklist id="c" value={[]} onChange={onChange} exclude="a" />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    expect(onChange).toHaveBeenLastCalledWith(["b"]);
    expect(screen.getByText(/choose at least one/)).toBeTruthy();
  });

  it("shows the error", () => {
    render(
      <CompanyChecklist id="c" value={[]} onChange={vi.fn()} error="Choose at least one company" />,
    );
    expect(screen.getByRole("alert").textContent).toBe("Choose at least one company");
  });
});
