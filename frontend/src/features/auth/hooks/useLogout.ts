import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { logout } from "@/services/session";

export type Logout = { logout: () => Promise<void>; signingOut: boolean };

/** Ends the session and empties the cache (the _app layout then sends us to /login).
 * The ref stops a double click from starting a second logout before React re-renders. */
export function useLogout(): Logout {
  const queryClient = useQueryClient();
  const [signingOut, setSigningOut] = useState(false);
  const signingOutRef = useRef(false);
  const run = useCallback(async (): Promise<void> => {
    if (signingOutRef.current) return;
    signingOutRef.current = true;
    setSigningOut(true);
    try {
      await logout();
      queryClient.clear();
    } finally {
      signingOutRef.current = false;
      setSigningOut(false);
    }
  }, [queryClient]);
  return { logout: run, signingOut };
}
