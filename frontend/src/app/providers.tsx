import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode, JSX } from "react";
import { Toaster } from "@/components/ui/sonner";
import { queryClient } from "@/app/queryClient";
import { Devtools } from "@/app/devtools";

export function Providers({ children }: { children: ReactNode }): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster />
      <Devtools />
    </QueryClientProvider>
  );
}
