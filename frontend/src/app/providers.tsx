import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";
import { queryClient } from "@/app/queryClient";
import { Devtools } from "@/app/devtools";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster />
      <Devtools />
    </QueryClientProvider>
  );
}
