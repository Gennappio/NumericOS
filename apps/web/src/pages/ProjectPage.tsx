import { PencilIcon } from "lucide-react"
import { useState } from "react"
import { Link, Outlet, useParams } from "react-router"
import { ApiError } from "@/api/client"
import { useBoard, useConnectionState, useProject, useRecentEvents } from "@/api/queries"
import { useEventStream, type Transport } from "@/api/useEventStream"
import { Board } from "@/components/board/Board"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
import { ProjectDialog } from "@/components/projects/ProjectDialog"
import { ViewTabs } from "@/components/projects/ViewTabs"
import { EventStrip } from "@/components/timeline/EventStrip"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { describeError } from "@/lib/errors"
import { useProjectContext, type ProjectContext } from "@/pages/projectContext"

export function ProjectPage() {
  const { projectId = "" } = useParams()
  // Keyed by project: switching project starts a clean page and a new event stream.
  return <ProjectFrame key={projectId} projectId={projectId} />
}

/** The frame of all views of one project: its name, its event stream, its view tabs. */
function ProjectFrame({ projectId }: { projectId: string }) {
  const offline = useConnectionState().state === "unreachable"
  const stream = useEventStream(projectId)
  // Never claim live updates while the backend is known to be unreachable.
  const transport: Transport = offline && stream === "live" ? "reconnecting" : stream
  const live = transport === "live"
  const project = useProject(projectId, live)
  const [editing, setEditing] = useState(false)

  if (project.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading project…
      </p>
    )
  }
  if (!project.data) {
    const missing =
      project.error instanceof ApiError &&
      project.error.status === 404 &&
      project.error.details.resource === "project"
    if (missing) {
      return (
        <section className="space-y-3">
          <h1 className="text-2xl font-semibold">Project not found</h1>
          <p className="text-sm text-muted-foreground">
            No project has the ID <span className="font-mono">{projectId}</span>.
          </p>
          <Link to="/" className="text-sm underline underline-offset-4">
            Back to all projects
          </Link>
        </section>
      )
    }
    return (
      <ErrorPanel
        title="Could not load the project"
        error={project.error}
        onRetry={() => void project.refetch()}
      />
    )
  }

  const data = project.data
  const context: ProjectContext = { project: data, transport, live, offline }
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold break-words">{data.name}</h1>
          {data.is_demo && <Badge variant="outline">Demo data</Badge>}
        </div>
        <Button variant="outline" onClick={() => setEditing(true)} disabled={offline}>
          <PencilIcon data-icon="inline-start" />
          Edit project
        </Button>
      </header>

      <ViewTabs projectId={data.id} />

      <Outlet context={context} />

      <ProjectDialog open={editing} onOpenChange={setEditing} project={data} />
    </div>
  )
}

/** The scientific board of a project, with what the project is about and its recent events. */
export function BoardView() {
  const { project, transport, live, offline } = useProjectContext()
  const board = useBoard(project.id, live)
  const events = useRecentEvents(project.id, live)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="space-y-5">
      <dl className="grid gap-4 rounded-lg border border-border bg-card p-4 md:grid-cols-[2fr_1fr]">
        <div className="min-w-0">
          <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Research question
          </dt>
          <dd className="mt-1 text-base break-words">
            {project.research_question || (
              <span className="text-muted-foreground">Not stated yet</span>
            )}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Project reference
          </dt>
          <dd className="mt-1 font-mono text-sm break-all">
            {project.root_path ?? (
              <span className="font-sans text-muted-foreground">No code path linked</span>
            )}
          </dd>
          <dd className="mt-1 font-mono text-xs break-all text-muted-foreground">{project.id}</dd>
        </div>
      </dl>
      {project.description && (
        <p className="max-w-prose text-sm whitespace-pre-line text-muted-foreground">
          {project.description}
        </p>
      )}

      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}

      {board.data ? (
        <Board
          projectId={project.id}
          board={board.data}
          disabled={offline}
          onError={(error) => setNotice(describeError(error))}
        />
      ) : board.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading board…
        </p>
      ) : (
        <ErrorPanel
          title="Could not load the board"
          error={board.error}
          onRetry={() => void board.refetch()}
        />
      )}

      <EventStrip projectId={project.id} page={events.data} transport={transport} />
    </div>
  )
}
