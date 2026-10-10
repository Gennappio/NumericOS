import { PlusIcon } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { useConnectionState, useProjects } from "@/api/queries"
import { ErrorPanel } from "@/components/ErrorPanel"
import { ProjectDialog } from "@/components/projects/ProjectDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { formatTimestamp } from "@/lib/time"

export function ProjectsPage() {
  const projects = useProjects()
  const offline = useConnectionState().state === "unreachable"
  const [creating, setCreating] = useState(false)

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Each project is one research question with its own scientific board.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={offline}>
          <PlusIcon data-icon="inline-start" />
          New project
        </Button>
      </div>

      {projects.isPending && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading projects…
        </p>
      )}
      {projects.isError && !projects.data && (
        <ErrorPanel
          title="Could not load projects"
          error={projects.error}
          onRetry={() => void projects.refetch()}
        />
      )}
      {projects.data?.projects.length === 0 && (
        <div className="space-y-2 rounded-lg border border-dashed border-border p-6">
          <h2 className="text-base font-medium">No projects yet</h2>
          <p className="text-sm text-muted-foreground">
            Create a project to organise its hypotheses, experiments, issues and decisions on a
            board. The same can be done from a terminal with{" "}
            <code>numericos project add &quot;My study&quot;</code>;{" "}
            <code>numericos seed-demo</code> adds one clearly marked demo project.
          </p>
        </div>
      )}
      {projects.data && projects.data.projects.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {projects.data.projects.map((project) => (
            <li key={project.id}>
              <Link
                to={`/projects/${project.id}`}
                className="block h-full space-y-2 rounded-lg border border-border bg-card p-4 hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-medium break-words">{project.name}</h2>
                  {project.is_demo && <Badge variant="outline">Demo data</Badge>}
                </div>
                <p className="text-sm break-words text-muted-foreground">
                  {project.research_question || "No research question stated yet"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Updated {formatTimestamp(project.updated_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <ProjectDialog open={creating} onOpenChange={setCreating} />
    </section>
  )
}
