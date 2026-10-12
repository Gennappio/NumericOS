import type { ReactNode } from "react"
import { Link, NavLink, useMatch } from "react-router"
import { API_URL } from "@/api/client"
import { useConnectionState, useProjects } from "@/api/queries"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ProjectNav } from "@/components/layout/ProjectNav"
import { formatClock } from "@/lib/time"
import { cn } from "@/lib/utils"

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm",
    isActive
      ? "bg-indigo-50 font-medium text-indigo-950"
      : "text-muted-foreground hover:bg-muted/60",
  )

/**
 * The frame of every page. The sidebar is the map of the work: every project, and under each
 * project's name its conversations with the coding agent.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const connection = useConnectionState()
  const projects = useProjects()
  const openProjectId = useMatch("/projects/:projectId/*")?.params.projectId
  const conversationId = useMatch("/projects/:projectId/conversations/:sessionId")?.params
    .sessionId

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground md:flex-row">
      <aside className="border-b border-border md:w-64 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-baseline gap-2 px-4 py-3">
          <Link to="/" className="text-base font-semibold text-indigo-700">
            NumericOS
          </Link>
          <span className="text-xs text-muted-foreground">pre-alpha</span>
        </div>
        <nav aria-label="Projects" className="px-2 pb-3">
          <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto md:max-h-none md:overflow-visible">
            <li>
              <NavLink to="/" end className={navLinkClass}>
                All projects
              </NavLink>
            </li>
            {projects.data?.projects.map((project) => (
              <ProjectNav
                key={project.id}
                project={project}
                open={project.id === openProjectId}
                conversationId={project.id === openProjectId ? conversationId : undefined}
                offline={connection.state === "unreachable"}
              />
            ))}
          </ul>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-b border-border px-4 py-2">
          <ConnectionStatus />
        </header>
        {connection.state === "unreachable" && (
          <div
            role="alert"
            className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-900"
          >
            The NumericOS API at {API_URL} is not reachable.{" "}
            {connection.lastContactAt
              ? `What you see is the last state received at ${formatClock(connection.lastContactAt)}, not live data.`
              : "Nothing could be loaded."}{" "}
            Changes are disabled until it is back (start it with <code>make api</code>).
          </div>
        )}
        <main className="flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  )
}
