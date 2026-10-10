import { Badge } from "@/components/ui/badge"

/** Views promised by the roadmap. They stay disabled until their milestone ships. */
const PLANNED_VIEWS = [
  { name: "Experiments", milestone: "M3" },
  { name: "Timeline", milestone: "M3" },
  { name: "Agents", milestone: "M1" },
  { name: "Knowledge", milestone: "M2" },
] as const

export function ViewTabs() {
  return (
    <nav aria-label="Project views" className="flex gap-1 overflow-x-auto border-b border-border">
      <span
        aria-current="page"
        className="-mb-px border-b-2 border-foreground px-3 py-2 text-sm font-medium"
      >
        Board
      </span>
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
