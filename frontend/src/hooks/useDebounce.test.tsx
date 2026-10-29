// @vitest-environment jsdom
// The shared debounce: one call with the final value after typing pauses.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDebounce, useDebouncedCallback } from "./useDebounce";

beforeEach(() => vi.useFakeTimers());

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const advanceTimers = async (ms: number): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

describe("useDebouncedCallback", () => {
  it("calls once, with the last value, 300 ms after the last call", async () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn));

    act(() => {
      result.current("l");
      result.current("la");
      result.current("lak");
    });

    await advanceTimers(299);
    expect(fn).not.toHaveBeenCalled();

    await advanceTimers(1);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("lak");
  });

  it("each new call restarts the wait", async () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn, 300));

    act(() => result.current("a"));
    await advanceTimers(200);

    act(() => result.current("ab"));
    await advanceTimers(200);

    expect(fn).not.toHaveBeenCalled();

    await advanceTimers(100);
    expect(fn).toHaveBeenCalledExactlyOnceWith("ab");
  });

  it("flush runs the waiting call now; cancel drops it", async () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn));

    act(() => result.current("now"));
    act(() => result.current.flush());

    expect(fn).toHaveBeenCalledExactlyOnceWith("now");

    act(() => result.current.flush());
    expect(fn).toHaveBeenCalledTimes(1);

    act(() => result.current("dropped"));
    act(() => result.current.cancel());

    await advanceTimers(1000);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("always calls the latest function, and nothing after unmount", async () => {
    const first = vi.fn();
    const second = vi.fn();

    const { result, rerender, unmount } = renderHook(({ fn }) => useDebouncedCallback(fn), {
      initialProps: { fn: first },
    });

    const stable = result.current;

    act(() => result.current("x"));
    rerender({ fn: second });

    expect(result.current).toBe(stable);

    await advanceTimers(300);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledExactlyOnceWith("x");

    act(() => result.current("y"));
    unmount();

    await advanceTimers(300);
    expect(second).toHaveBeenCalledTimes(1);
  });
});

describe("useDebounce", () => {
  it("returns the value once it has stopped changing", async () => {
    const { result, rerender } = renderHook(({ v }) => useDebounce(v), {
      initialProps: { v: "" },
    });

    rerender({ v: "g" });
    rerender({ v: "gr" });

    expect(result.current).toBe("");

    await advanceTimers(300);
    expect(result.current).toBe("gr");
  });
});
