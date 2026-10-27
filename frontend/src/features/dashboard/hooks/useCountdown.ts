import { useEffect, useState } from "react";

/**
 * Seconds left of a countdown the server started: `seconds` as of `since` (ms, e.g. the
 * query's dataUpdatedAt). Ticks from a timer, so render never reads the clock.
 */
export function useCountdown(seconds: number, since: number): number {
  const [tick, setTick] = useState<{ since: number; left: number } | null>(null);
  useEffect(() => {
    if (seconds <= 0) return;
    const until = since + seconds * 1000;
    const id = setInterval(() => {
      const left = Math.max(0, Math.ceil((until - Date.now()) / 1000));
      setTick({ since, left });
      if (left === 0) clearInterval(id);
    }, 250);
    return () => clearInterval(id);
  }, [seconds, since]);
  return tick && tick.since === since ? tick.left : Math.max(0, seconds);
}
