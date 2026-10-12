import { useState } from "react"
import type { Project } from "@/api/client"
import { useGeneratePlan, usePlan } from "@/api/queries"
import type { AgentReadiness } from "@/components/agent/readiness"
import { GenerateForm } from "@/components/documents/GenerateForm"
import { GenerationProgress } from "@/components/documents/GenerationProgress"
import { Markdown } from "@/components/markdown/Markdown"
import { formatTimestamp } from "@/lib/time"

interface PlanPanelProps {
  project: Project
  live: boolean
  readiness: AgentReadiness
  onError: (error: unknown) => void
}

/**
 * The plan of the agent. Asked, the agent reads the repository and the board as it is and
 * answers with cards, which are put on the board: new ones at the end of their column, and
 * the changes it made to cards that were there. Its reasons are kept here. The cards are then
 * yours: move them, edit them, add your own, and ask again.
 */
export function PlanPanel({ project, live, readiness, onError }: PlanPanelProps) {
  const plan = usePlan(project.id, live)
  const generate = useGeneratePlan(project.id)
  const [asking, setAsking] = useState(false)
  const document = plan.data?.document ?? null
  const pending = Boolean(document?.pending_message_id)

  return (
    <section aria-label="Plan" className="space-y-3 rounded-lg border border-border bg-card p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-prose">
          <h2 className="text-base font-medium">Plan</h2>
          <p className="text-sm text-muted-foreground">
            The board below is the plan of the project. Ask the agent to propose it from the
            repository, then drag the cards, edit them or add your own: the next request starts
            from the board as you left it.
          </p>
        </div>
        {!asking && !pending && (
          <button
            type="button"
            className="text-sm font-medium underline underline-offset-4"
            onClick={() => setAsking(true)}
          >
            {document && document.version > 0 ? "Ask the agent to plan again…" : "Ask the agent to plan…"}
          </button>
        )}
      </header>

      {pending && document && (
        <GenerationProgress
          projectId={project.id}
          messageId={document.pending_message_id!}
          sessionId={document.session_id}
          label="The agent is planning"
          supervisorAlive={readiness.supervisorAlive}
          onError={onError}
        />
      )}

      {asking && !pending && (
        <GenerateForm
          action="Ask for a plan"
          instructions={document?.instructions ?? ""}
          blocked={readiness.blocked}
          pending={generate.isPending}
          hint="For example: Scrivi in italiano. Concentrati sulla validazione numerica."
          onGenerate={(instructions) =>
            generate.mutate(instructions, { onSuccess: () => setAsking(false), onError })
          }
        />
      )}

      {document && document.status === "failed" && !pending && (
        <p role="alert" className="text-sm text-red-800">
          The last request did not produce a plan: {document.status_reason}
        </p>
      )}

      {document && document.version > 0 && (
        <details className="text-sm" open={!pending}>
          <summary className="cursor-pointer text-muted-foreground">
            Last plan of the agent: {document.summary}
            {document.generated_at && <> · {formatTimestamp(document.generated_at)}</>}
          </summary>
          <div className="mt-2 border-t border-border pt-2">
            {document.markdown ? (
              <Markdown source={document.markdown} />
            ) : (
              <p className="text-muted-foreground">The agent gave no reasons.</p>
            )}
            {document.status_reason && (
              <p role="alert" className="mt-2 text-sm text-red-800">
                The last request to plan again did not succeed: {document.status_reason}
              </p>
            )}
          </div>
        </details>
      )}
    </section>
  )
}
