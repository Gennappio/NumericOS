import type { ReactNode } from "react"
import { Link, NavLink } from "react-router"
import { API_URL } from "@/api/client"
import { useConnectionState, useProjects } from "@/api/queries"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { Badge } from "@/components/ui/badge"
import { formatClock } from "@/lib/time"
import { cn } from "@/lib/utils"

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm",
    isActive
      ? "bg-indigo-50 font-medium text-indigo-950"
      : "text-muted-foreground hover:bg-muted/60",
  )

const PROJECT_DOTS = [
  "bg-indigo-500",
  "bg-fuchsia-500",
  "bg-cyan-500",
  "bg-amber-500",
  "bg-violet-500",
  "bg-sky-500",
  "bg-pink-500",
  "bg-teal-500",
]

/** The same colour for the same project every time, to tell projects apart at a glance. */
function projectDot(id: string): string {
  let sum = 0
  for (const character of id) sum = (sum * 31 + character.charCodeAt(0)) % 9973
  return PROJECT_DOTS[sum % PROJECT_DOTS.length]
}

export function AppShell({ children }: { children: ReactNode }) {
  const connection = useConnectionState()
  const projects = useProjects()

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
          <ul className="flex gap-1 overflow-x-auto md:flex-col md:overflow-visible">
            <li className="shrink-0">
              <NavLink to="/" end className={navLinkClass}>
                All projects
              </NavLink>
            </li>
            {projects.data?.projects.map((project) => (
              <li key={project.id} className="shrink-0 md:shrink">
                <NavLink to={`/projects/${project.id}`} className={navLinkClass}>
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      aria-hidden="true"
                      className={cn("inline-block size-2.5 shrink-0 rounded-full", projectDot(project.id))}
                    />
                    <span className="break-words">{project.name}</span>
                  </span>
                  {project.is_demo && <Badge variant="outline">Demo</Badge>}
                </NavLink>
              </li>
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
