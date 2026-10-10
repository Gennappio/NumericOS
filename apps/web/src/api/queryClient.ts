import { QueryClient } from "@tanstack/react-query"
import { ApiError } from "./client"

/** Typed API answers (404, 409, 422) are results, not transient failures: never retry them. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => !(error instanceof ApiError) && failureCount < 1,
        refetchOnWindowFocus: true,
      },
    },
  })
}
