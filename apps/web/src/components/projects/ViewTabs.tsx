import { Link, useLocation } from "react-router"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/** Views promised by the roadmap. They stay disabled until their milestone ships. */
const PLANNED_VIEWS = [
  { name: "Timeline", milestone: "M3" },
  { name: "Knowledge", milestone: "M2" },
] as const

/** The views of a project. A view that does not exist yet is shown as such, never faked. */
export function ViewTabs({ projectId }: { projectId: string }) {
  const { pathname } = useLocation()
  const base = `/projects/${projectId}`
  // The pages of single experiments and runs belong to the experiments view.
  const inExperiments =
    pathname.startsWith(`${base}/experiments`) || pathname.startsWith(`${base}/runs/`)
  const inAgent = pathname.startsWith(`${base}/agent`)
  const views = [
    { name: "Board", to: base, current: !inExperiments && !inAgent },
    { name: "Experiments", to: `${base}/experiments`, current: inExperiments },
    { name: "Agent", to: `${base}/agent`, current: inAgent },
  ]
  return (
    <nav aria-label="Project views" className="flex gap-1 overflow-x-auto border-b border-border">
      {views.map((view) => (
        <Link
          key={view.name}
          to={view.to}
          aria-current={view.current ? "page" : undefined}
          className={cn(
            "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm",
            view.current
              ? "border-foreground font-medium text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {view.name}
        </Link>
      ))}
      {PLANNED_VIEWS.map((view) => (
        <button
          key={view.name}
          type="button"
          disabled
          aria-disabled="true"
          title={`${view.name}: planned for milestone ${view.milestone}, not available yet`}
          className="flex shrink-0 items-center gap-2 px-3 py-2 text-sm text-muted-foreground opacity-60"
        >
          <span>{view.name}</span>
          <Badge variant="outline">{view.milestone}</Badge>
        </button>
      ))}
    </nav>
  )
}
