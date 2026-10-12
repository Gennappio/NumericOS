import type { AgentCapabilities, Project } from "@/api/client"
import { useAgentCapabilities, useWorkers } from "@/api/queries"

export interface AgentReadiness {
  /** Why nothing can be asked of the agent right now, if anything stands in the way. */
  blocked: string | null
  /** A supervisor is alive to serve the turns that are queued. */
  supervisorAlive: boolean
  capabilities: AgentCapabilities | undefined
  capabilitiesError: unknown
}

/**
 * Whether the agent can work on this project, as it is: the project has a directory, the
 * directory was trusted, the agent command was found, a supervisor is alive.
 */
export function useAgentReadiness(project: Project, offline: boolean): AgentReadiness {
  const capabilities = useAgentCapabilities()
  const workers = useWorkers()
  let blocked: string | null = null
  if (offline) blocked = "The NumericOS API is not reachable."
  else if (project.root_path === null) {
    blocked = "This project has no code path: set it with Edit project."
  } else if (!project.execution_trusted_at) {
    blocked = "Execution in the project directory is not allowed yet."
  } else if (capabilities.data && !capabilities.data.available) {
    blocked = `The agent command is not available: ${capabilities.data.problem ?? "unknown reason"}`
  }
  return {
    blocked,
    supervisorAlive: (workers.data?.alive ?? 0) > 0,
    capabilities: capabilities.data,
    capabilitiesError: capabilities.error,
  }
}
