import { useOutletContext } from "react-router"
import type { Project } from "@/api/client"
import type { Transport } from "@/api/useEventStream"

/** What every view of a project gets from the page that frames it. */
export interface ProjectContext {
  project: Project
  transport: Transport
  /** Every change of the project arrives as an event; otherwise views fall back to polling. */
  live: boolean
  /** The backend is known to be unreachable: nothing can be changed. */
  offline: boolean
}

export function useProjectContext(): ProjectContext {
  return useOutletContext<ProjectContext>()
}
