import { Link } from "react-router"
import { isTurnActive, useCancelMessage, useMessage } from "@/api/queries"
import { ActivityList } from "@/components/agent/ActivityList"
import { TurnStatusBadge } from "@/components/agent/TurnStatusBadge"
import { Button } from "@/components/ui/button"

interface GenerationProgressProps {
  projectId: string
  /** The turn that is writing the document. */
  messageId: string
  sessionId: string | null | undefined
  /** What the agent is doing, in a few words: "Writing the theory". */
  label: string
  supervisorAlive: boolean
  onError: (error: unknown) => void
}

/**
 * A document while the agent writes it: how its turn stands and every action of the agent as
 * it is recorded, with a way to stop it and to open the whole conversation.
 */
export function GenerationProgress({
  projectId,
  messageId,
  sessionId,
  label,
  supervisorAlive,
  onError,
}: GenerationProgressProps) {
  const message = useMessage(projectId, messageId)
  const cancel = useCancelMessage(projectId, sessionId ?? "")
  const turn = message.data
  return (
    <section
      aria-label={label}
      data-generating="true"
      className="space-y-3 rounded-lg border border-sky-300 bg-sky-50/60 p-4"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-medium">{label}</span>
          {turn && <TurnStatusBadge status={turn.status} />}
          {turn?.model_requested && (
            <span className="text-xs text-muted-foreground">model {turn.model_requested}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <Link
              to={`/projects/${projectId}/agent/${sessionId}`}
              className="text-xs underline underline-offset-4"
            >
              Open the agent&apos;s work
            </Link>
          )}
          {turn && isTurnActive(turn.status) && (
            <Button
              variant="outline"
              size="sm"
              disabled={cancel.isPending}
              onClick={() =>
                cancel.mutate({ messageId, reason: "stopped from the page" }, { onError })
              }
            >
              Stop
            </Button>
          )}
        </div>
      </header>
      {turn?.status === "queued" && (
        <p className="text-sm text-muted-foreground">
          Waiting for a supervisor to start the agent.
          {!supervisorAlive && (
            <>
              {" "}
              <span className="font-medium text-amber-800">No supervisor is running.</span> Start
              one with <code className="font-mono text-xs">make worker</code>.
            </>
          )}
        </p>
      )}
      {turn && turn.status !== "queued" && (
        <ActivityList items={turn.activity} dropped={turn.activity_dropped} />
      )}
    </section>
  )
}
