import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, type CardCreate, type CardPatch, type ProjectPatch } from "./client"

export const queryKeys = {
  health: ["health"] as const,
  projects: ["projects"] as const,
  project: (projectId: string) => ["projects", projectId] as const,
  board: (projectId: string) => ["projects", projectId, "board"] as const,
}

/**
 * Bounded re-reads of real backend state, so changes made elsewhere (CLI, another tab) show up.
 * The replayable event stream (M0-T05) will drive refreshes; polling stays as its fallback.
 */
const POLL_MS = 5_000

/** Polls the API liveness endpoint; the result drives every "is the backend live?" indicator. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: POLL_MS,
    retry: 0,
    staleTime: 2_000,
  })
}

export type ConnectionState = "checking" | "connected" | "unreachable"

export interface ConnectionInfo {
  state: ConnectionState
  version?: string
  /** True when the API answers but reports a degraded database (e.g. pending migrations). */
  degraded?: boolean
  /** Epoch milliseconds of the last successful health check, if there was one. */
  lastContactAt?: number
}

/** Derived from the live health query: an error always wins over previously cached data. */
export function useConnectionState(): ConnectionInfo {
  const health = useHealth()
  const lastContactAt = health.dataUpdatedAt || undefined
  if (health.status === "error") return { state: "unreachable", lastContactAt }
  if (health.status === "success") {
    return {
      state: "connected",
      version: health.data.version,
      degraded: health.data.status === "degraded",
      lastContactAt,
    }
  }
  return { state: "checking" }
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: api.listProjects,
    refetchInterval: POLL_MS,
  })
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => api.getProject(projectId),
    refetchInterval: POLL_MS,
  })
}

export function useBoard(projectId: string) {
  return useQuery({
    queryKey: queryKeys.board(projectId),
    queryFn: () => api.getBoard(projectId),
    refetchInterval: POLL_MS,
  })
}

// Mutations return the invalidation promise from `onSettled`: the mutation stays pending until
// the refreshed data (with the new record versions) is on screen, so a second action can never
// be sent with a stale version by accident.

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.createProject,
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: ProjectPatch) => api.updateProject(projectId, patch),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useCreateCard(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (card: CardCreate) => api.createCard(projectId, card),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.board(projectId) }),
  })
}

export function useUpdateCard(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    // The project assertion makes the API refuse a card that belongs to another project.
    mutationFn: ({ cardId, patch }: { cardId: string; patch: CardPatch }) =>
      api.updateCard(cardId, { ...patch, project_id: projectId }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.board(projectId) }),
  })
}
