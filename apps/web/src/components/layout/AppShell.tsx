import type { ReactNode } from "react"
import { NavLink } from "react-router"
import { API_URL } from "@/api/client"
import { useConnectionState } from "@/api/queries"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/** Views promised by the roadmap. They are rendered disabled until their milestone ships. */
const PLANNED_VIEWS = [
  { name: "Experiments", milestone: "M3" },
  { name: "Timeline", milestone: "M3" },
  { name: "Agents", milestone: "M1" },
  { name: "Knowledge", milestone: "M2" },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  const { state } = useConnectionState()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground md:flex-row">
      <aside className="border-b border-border md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="px-4 py-3 text-base font-semibold">NumericOS</div>
        <nav
          aria-label="Project views"
          className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4"
        >
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(
                "rounded-md px-3 py-2 text-sm font-medium",
                isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60",
              )
            }
          >
            Board
          </NavLink>
          {PLANNED_VIEWS.map((view) => (
            <button
              key={view.name}
              type="button"
              disabled
              aria-disabled="true"
              title={`${view.name}: planned for milestone ${view.milestone}, not available yet`}
              className="flex items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm text-muted-foreground opacity-60"
            >
              <span>{view.name}</span>
              <Badge variant="outline">{view.milestone}</Badge>
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border px-4 py-3">
          <span className="text-sm text-muted-foreground">Milestone M0 · foundations</span>
          <ConnectionStatus />
        </header>
        {state === "unreachable" && (
          <div
            role="alert"
            className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100"
          >
            The NumericOS API at {API_URL} is not reachable. Start it with <code>make api</code>;
            nothing shown here is live until it is back.
          </div>
        )}
        <main className="flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  )
}
