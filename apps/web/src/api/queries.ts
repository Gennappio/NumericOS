import { useQuery } from "@tanstack/react-query"
import { fetchHealth } from "./client"

export const queryKeys = {
  health: ["health"] as const,
}

/** Polls the API liveness endpoint; the result drives every "is the backend live?" indicator. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    refetchInterval: 10_000,
    retry: 0,
    staleTime: 5_000,
  })
}

export type ConnectionState = "checking" | "connected" | "unreachable"

export interface ConnectionInfo {
  state: ConnectionState
  version?: string
  /** True when the API answers but reports a degraded database (e.g. pending migrations). */
  degraded?: boolean
}

/** Derived from the live health query: an error always wins over previously cached data. */
export function useConnectionState(): ConnectionInfo {
  const health = useHealth()
  if (health.status === "error") return { state: "unreachable" }
  if (health.status === "success") {
    return {
      state: "connected",
      version: health.data.version,
      degraded: health.data.status === "degraded",
    }
  }
  return { state: "checking" }
}
