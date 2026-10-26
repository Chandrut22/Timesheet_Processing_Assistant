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

describe("useDebouncedCallback", () => {
  it("calls once, with the last value, 300 ms after the last call", () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn));
    act(() => {
      result.current("l");
      result.current("la");
      result.current("lak");
    });
    act(() => vi.advanceTimersByTime(299));
    expect(fn).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("lak");
  });

  it("each new call restarts the wait", () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn, 300));
    act(() => result.current("a"));
    act(() => vi.advanceTimersByTime(200));
    act(() => result.current("ab"));
    act(() => vi.advanceTimersByTime(200));
    expect(fn).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(100));
    expect(fn).toHaveBeenCalledExactlyOnceWith("ab");
  });

  it("flush runs the waiting call now; cancel drops it", () => {
    const fn = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(fn));
    act(() => result.current("now"));
    act(() => result.current.flush());
    expect(fn).toHaveBeenCalledExactlyOnceWith("now");
    act(() => result.current.flush()); // nothing waiting
    expect(fn).toHaveBeenCalledTimes(1);

    act(() => result.current("dropped"));
    act(() => result.current.cancel());
    act(() => vi.advanceTimersByTime(1000));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("always calls the latest function, and nothing after unmount", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender, unmount } = renderHook(({ fn }) => useDebouncedCallback(fn), {
      initialProps: { fn: first },
    });
    const stable = result.current;
    act(() => result.current("x"));
    rerender({ fn: second });
    expect(result.current).toBe(stable); // same function across renders
    act(() => vi.advanceTimersByTime(300));
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledExactlyOnceWith("x");

    act(() => result.current("y"));
    unmount();
    vi.advanceTimersByTime(300);
    expect(second).toHaveBeenCalledTimes(1);
  });
});

describe("useDebounce", () => {
  it("returns the value once it has stopped changing", () => {
    const { result, rerender } = renderHook(({ v }) => useDebounce(v), {
      initialProps: { v: "" },
    });
    rerender({ v: "g" });
    rerender({ v: "gr" });
    expect(result.current).toBe("");
    act(() => vi.advanceTimersByTime(300));
    expect(result.current).toBe("gr");
  });
});
