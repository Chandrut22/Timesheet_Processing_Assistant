import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

export function Devtools() {
  if (!import.meta.env.DEV) return null;
  return <ReactQueryDevtools buttonPosition="bottom-left" />;
}