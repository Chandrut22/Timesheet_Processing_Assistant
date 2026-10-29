import { useSyncExternalStore } from "react";
import {
  getSession,
  subscribeSession,
  type SessionUser,
  type SessionState,
} from "@/services/session";

export function useSession(): SessionState {
  return useSyncExternalStore(subscribeSession, getSession, getSession);
}

/** The signed-in user. Only use inside the protected (_app) routes. */
export function useUser(): SessionUser {
  const s = useSession();
  if (!s.user) throw new Error("useUser() used outside a signed-in route");
  return s.user;
}

export function useIsAdmin(): boolean {
  return useSession().user?.role === "admin";
}
