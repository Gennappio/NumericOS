import {
  BookOpenTextIcon,
  BotIcon,
  FlaskConicalIcon,
  FolderTreeIcon,
  SquareKanbanIcon,
} from "lucide-react"
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
  const inTheory = pathname.startsWith(`${base}/theory`)
  const inFiles = pathname.startsWith(`${base}/files`)
  // A conversation is opened from the sidebar and is none of the views: no tab is current.
  const inConversation = pathname.startsWith(`${base}/conversations/`)
  // What the project is (theory, files), what is to be done (plan), then the work itself.
  // Each view has its colour: it marks the tab, and what belongs to the view elsewhere.
  const views = [
    {
      name: "Plan",
      to: base,
      current: !inExperiments && !inAgent && !inTheory && !inFiles && !inConversation,
      icon: SquareKanbanIcon,
      tint: "text-indigo-500",
      active: "border-indigo-600 text-indigo-700",
    },
    {
      name: "Theory",
      to: `${base}/theory`,
      current: inTheory,
      icon: BookOpenTextIcon,
      tint: "text-violet-500",
      active: "border-violet-600 text-violet-700",
    },
    {
      name: "Files",
      to: `${base}/files`,
      current: inFiles,
      icon: FolderTreeIcon,
      tint: "text-sky-500",
      active: "border-sky-600 text-sky-700",
    },
    {
      name: "Agent",
      to: `${base}/agent`,
      current: inAgent,
      icon: BotIcon,
      tint: "text-fuchsia-500",
      active: "border-fuchsia-600 text-fuchsia-700",
    },
    {
      name: "Experiments",
      to: `${base}/experiments`,
      current: inExperiments,
      icon: FlaskConicalIcon,
      tint: "text-cyan-600",
      active: "border-cyan-600 text-cyan-700",
    },
  ]
  return (
    <nav aria-label="Project views" className="flex gap-1 overflow-x-auto border-b border-border">
      {views.map((view) => (
        <Link
          key={view.name}
          to={view.to}
          aria-current={view.current ? "page" : undefined}
          className={cn(
            "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm",
            view.current
              ? cn("font-medium", view.active)
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <view.icon aria-hidden="true" className={cn("size-4", view.tint)} />
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
