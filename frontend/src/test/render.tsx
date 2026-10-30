// Shared test helper: render a component inside a fresh QueryClient that never retries,
// so a failing request shows its error state at once.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { JSX, ReactElement, ReactNode } from "react";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

export function renderWithClient(
  ui: ReactElement,
  client: QueryClient = testQueryClient(),
): RenderResult & { client: QueryClient } {
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}

/** For renderHook: the hook runs inside this client. */
export function clientWrapper(
  client: QueryClient,
): (props: { children: ReactNode }) => JSX.Element {
  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}
