import { QueryCache, MutationCache, QueryClient } from "@tanstack/react-query";

const notify = (error: unknown) => {
  // replace with your toast; map backend error codes to plain messages
  console.error(error);
};

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: notify }),
  mutationCache: new MutationCache({ onError: notify }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});