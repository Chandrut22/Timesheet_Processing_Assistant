// Debouncing for search boxes: the box shows every keystroke at once, the API is only
// asked once typing pauses. One implementation for the whole app.
import { useEffect, useLayoutEffect, useState } from "react";
import { SEARCH_DEBOUNCE_MS } from "@/config/constants";

/** `value`, but only after it has stopped changing for `delay` ms. */
export function useDebounce<T>(value: T, delay = SEARCH_DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export type DebouncedCallback<A extends unknown[]> = ((...args: A) => void) & {
  /** Run the waiting call now (e.g. on Enter). Does nothing when none is waiting. */
  flush: () => void;
  /** Drop the waiting call. */
  cancel: () => void;
};

type Debouncer<A extends unknown[]> = DebouncedCallback<A> & {
  /** Use the latest `fn` and `delay` (set from an effect after every render). */
  configure: (fn: (...args: A) => void, delay: number) => void;
};

/** Plain closures, no React refs, so it is safe to create during render. */
function createDebouncer<A extends unknown[]>(
  initialFn: (...args: A) => void,
  initialDelay: number,
): Debouncer<A> {
  let target = initialFn;
  let delay = initialDelay;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: A | null = null;
  const cancel = (): void => {
    clearTimeout(timer);
    timer = undefined;
    pending = null;
  };
  const flush = (): void => {
    const args = pending;
    cancel();
    if (args) target(...args);
  };
  const call = (...args: A): void => {
    clearTimeout(timer);
    pending = args;
    timer = setTimeout(flush, delay);
  };
  return Object.assign(call, {
    flush,
    cancel,
    configure: (fn: (...args: A) => void, ms: number) => {
      target = fn;
      delay = ms;
    },
  });
}

/**
 * A stable function that calls `fn` with the last arguments once calls have stopped
 * for `delay` ms. Always calls the latest `fn` (no stale closures), and drops a
 * waiting call when the component unmounts.
 */
export function useDebouncedCallback<A extends unknown[]>(
  fn: (...args: A) => void,
  delay = SEARCH_DEBOUNCE_MS,
): DebouncedCallback<A> {
  // Created once per component; later renders only update its target and delay.
  const [debounced] = useState(() => createDebouncer(fn, delay));
  useLayoutEffect(() => {
    debounced.configure(fn, delay);
  });
  useEffect(() => debounced.cancel, [debounced]);
  return debounced;
}
