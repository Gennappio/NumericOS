import { useId, useState, type FormEvent } from "react"
import type { Message } from "@/api/client"
import { isTurnActive, useMoveCreatedFiles } from "@/api/queries"
import { ActivityList } from "@/components/agent/ActivityList"
import { TurnStatusBadge } from "@/components/agent/TurnStatusBadge"
import { Commentable } from "@/components/comments/Commentable"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { formatListCost, formatPlanUsage, formatTokens, turnDuration } from "@/lib/agent"

interface MessageCardProps {
  message: Message
  /** A supervisor is alive to serve queued turns. */
  supervisorAlive: boolean
  onStop?: (reason: string) => void
  /** Why the agent cannot be asked now, if so: an answer can still be read and commented. */
  blocked?: string | null
  onError?: (error: unknown) => void
}

/**
 * One message of a conversation. A prompt is shown as written. A turn of the agent shows what
 * is known about it at this moment: its state, what the agent did, what the permission mode
 * refused, what it cost, and the answer once there is one.
 */
export function MessageCard({
  message,
  supervisorAlive,
  onStop,
  blocked = null,
  onError = () => {},
}: MessageCardProps) {
  if (message.role === "user") {
    return (
      <article
        aria-label="Your message"
        data-role="user"
        className="ml-auto max-w-[85%] rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm whitespace-pre-wrap text-indigo-950"
      >
        {message.markdown}
      </article>
    )
  }
  const active = isTurnActive(message.status)
  const actions = message.activity.length + message.activity_dropped
  const duration = turnDuration(message)
  return (
    <article
      aria-label="Agent answer"
      data-role="assistant"
      className="space-y-3 rounded-lg border border-border bg-card p-4"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <TurnStatusBadge status={message.status} />
          {(message.model ?? message.model_requested) && (
            <span>model {message.model ?? message.model_requested}</span>
          )}
          {message.effort && <span>effort {message.effort}</span>}
          {message.usage && <span>{formatTokens(message.usage)}</span>}
          {message.cost_usd !== null && message.cost_usd !== undefined && (
            <span>{formatListCost(message.cost_usd)}</span>
          )}
          {duration && <span>{duration}</span>}
          {actions > 0 && <span>{actions === 1 ? "1 action" : `${actions} actions`}</span>}
          {message.plan_usage && <span>{formatPlanUsage(message.plan_usage)}</span>}
        </div>
        {active && onStop && <StopButton onStop={onStop} disabled={blocked !== null} />}
      </header>

      {message.status === "queued" && (
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
      {message.status === "running" && (
        <ActivityList items={message.activity} dropped={message.activity_dropped} />
      )}
      {message.status === "final" && (
        <Commentable
          projectId={message.project_id}
          target={{ type: "message", id: message.id }}
          source={message.markdown}
          version={1}
          layout="below"
          blocked={blocked}
          supervisorAlive={supervisorAlive}
          onError={onError}
        />
      )}
      {(message.status === "failed" ||
        message.status === "cancelled" ||
        message.status === "interrupted") && (
        <p role="alert" className="rounded-md border border-border bg-muted/50 px-3 py-2 text-sm">
          {message.status === "failed" && "The agent ended with an error"}
          {message.status === "cancelled" && "Stopped"}
          {message.status === "interrupted" && "No answer"}
          {message.status_reason && `: ${message.status_reason}`}
        </p>
      )}

      {message.permission_denials.length > 0 && (
        <section
          aria-label="Refused by the permission mode"
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        >
          <p className="font-medium">Refused by the permission mode of this conversation:</p>
          <ul className="mt-1 space-y-0.5">
            {message.permission_denials.map((denial, index) => (
              <li key={index}>
                {denial.tool_name}{" "}
                <span className="font-mono text-xs break-all">{denial.summary}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <CreatedFiles message={message} onError={onError} />

      {!active && actions > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            What the agent did ({actions === 1 ? "1 action" : `${actions} actions`}
            {message.files_read.length > 0 && `, read ${message.files_read.length} file(s)`}
            {message.files_written.length > 0 && `, changed ${message.files_written.length} file(s)`}
            )
          </summary>
          <div className="mt-2 space-y-2 border-t border-border pt-2">
            <ActivityList items={message.activity} dropped={message.activity_dropped} />
            {message.files_written.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Files changed:{" "}
                <span className="font-mono break-all">{message.files_written.join(", ")}</span>
              </p>
            )}
          </div>
        </details>
      )}
    </article>
  )
}

/**
 * New files a turn left in the repository, outside the NumericOS folder. They are named, and
 * one click moves them to that folder: a file that belongs to the project is left by not
 * pressing it.
 */
function CreatedFiles({ message, onError }: { message: Message; onError: (error: unknown) => void }) {
  const move = useMoveCreatedFiles(message.project_id)
  const created = message.files_created ?? []
  const moved = new Set(message.files_moved ?? [])
  const left = created.filter((path) => !moved.has(path))
  if (created.length === 0) return null
  return (
    <section
      aria-label="New files in the repository"
      className={
        left.length > 0
          ? "space-y-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
          : "rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-950"
      }
    >
      {left.length > 0 ? (
        <>
          <p className="font-medium">
            This turn left {left.length === 1 ? "a new file" : `${left.length} new files`} in the
            repository:
          </p>
          <ul className="space-y-0.5 font-mono text-xs break-all">
            {left.map((path) => (
              <li key={path}>{path}</li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              className="border-amber-400 bg-white"
              disabled={move.isPending}
              onClick={() => move.mutate(message.id, { onError })}
            >
              Move {left.length === 1 ? "it" : "them"} to the NumericOS folder
            </Button>
            <span className="text-xs">
              Leave {left.length === 1 ? "it" : "them"} if {left.length === 1 ? "it is" : "they are"}{" "}
              part of the project.
            </span>
          </div>
        </>
      ) : (
        <p>
          {created.length === 1 ? "The file" : `The ${created.length} files`} this turn left in
          the repository {created.length === 1 ? "was" : "were"} moved to the NumericOS folder.
        </p>
      )}
    </section>
  )
}

function StopButton({ onStop, disabled }: { onStop: (reason: string) => void; disabled?: boolean }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onStop(reason.trim() || "stopped from the GUI")
    setOpen(false)
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={disabled}>
        Stop the agent…
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={submit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>Stop the agent</DialogTitle>
              <DialogDescription>
                The agent process is ended; what it did so far stays recorded. Files it already
                changed stay changed.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-1.5">
              <label htmlFor={`${id}-reason`} className="text-sm font-medium">
                Why (recorded with the turn)
              </label>
              <Input
                id={`${id}-reason`}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={300}
              />
            </div>
            <DialogFooter>
              <DialogClose render={<Button type="button" variant="outline" />}>Keep going</DialogClose>
              <Button type="submit">Stop the agent</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
