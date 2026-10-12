import { useId, useState, type FormEvent } from "react"
import type { Annotation, CommentTarget, PermissionMode } from "@/api/client"
import { useDismissAnnotation, useSendAnnotations } from "@/api/queries"
import { GenerationProgress } from "@/components/documents/GenerationProgress"
import { Markdown } from "@/components/markdown/Markdown"
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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { countOpen, excerpt, KIND_LABELS, KIND_STYLES, STATUS_LABELS } from "@/lib/comments"
import { cn } from "@/lib/utils"

interface CommentsPanelProps {
  projectId: string
  target: CommentTarget
  /** The comments of the text, without the withdrawn ones. */
  annotations: Annotation[]
  /** The list is of the version of the text on the page. */
  current: boolean
  pendingMessageId: string | null
  pendingSessionId: string | null
  focused: string | null
  layout: "side" | "below"
  blocked: string | null
  supervisorAlive: boolean
  onReveal: (annotation: Annotation) => void
  onError: (error: unknown) => void
}

/**
 * The comments on a text and the two buttons that send them to the agent. **Clarify** sends
 * every open clarification request in one turn: the answers appear next to their passages and
 * the text is not rewritten. **Resolve** sends every open change request in one turn: the
 * agent edits the files of the project, decides what to do when requests conflict, and may
 * rewrite the text.
 */
export function CommentsPanel({
  projectId,
  target,
  annotations,
  current,
  pendingMessageId,
  pendingSessionId,
  focused,
  layout,
  blocked,
  supervisorAlive,
  onReveal,
  onError,
}: CommentsPanelProps) {
  const send = useSendAnnotations(projectId, target)
  const dismiss = useDismissAnnotation(projectId, target)
  const [resolving, setResolving] = useState(false)
  const toClarify = countOpen(annotations, "clarification")
  const toResolve = countOpen(annotations, "change")
  const busy = pendingMessageId !== null || send.isPending

  // An answer without comments keeps the page as it was: the list appears with the first one.
  if (annotations.length === 0 && layout === "below") return null

  return (
    <aside
      aria-label="Comments"
      className={cn(
        "space-y-3 font-sans text-sm",
        layout === "side" && "xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto",
        layout === "below" && "rounded-lg border border-border bg-muted/30 p-3",
      )}
    >
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-medium">
            Comments <span className="font-normal text-muted-foreground">{annotations.length}</span>
          </h3>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              disabled={blocked !== null || busy || toClarify === 0}
              title="Send every open clarification request to the agent, in one turn"
              onClick={() => send.mutate({ action: "clarify" }, { onError })}
            >
              Clarify ({toClarify})
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={blocked !== null || busy || toResolve === 0}
              title="Send every open change request to the agent, which edits the files"
              onClick={() => setResolving(true)}
            >
              Resolve ({toResolve})…
            </Button>
          </div>
        </div>
        {annotations.length === 0 && (
          <p className="text-muted-foreground">
            Select any passage of the text to ask for a clarification, request a change or add
            a note. Clarify and Resolve then send the requests to the agent together.
          </p>
        )}
        {blocked && (toClarify > 0 || toResolve > 0) && (
          <p role="status" className="text-amber-800">
            {blocked}
          </p>
        )}
      </header>

      {pendingMessageId && (
        <GenerationProgress
          projectId={projectId}
          messageId={pendingMessageId}
          sessionId={pendingSessionId}
          label="The agent is answering the comments"
          supervisorAlive={supervisorAlive}
          onError={onError}
        />
      )}

      <ol className="space-y-2">
        {annotations.map((item) => (
          <li key={item.id}>
            <CommentCard
              item={item}
              attached={current && item.anchor_state === "attached"}
              focused={item.id === focused}
              onReveal={() => onReveal(item)}
              onDismiss={() => dismiss.mutate(item.id, { onError })}
            />
          </li>
        ))}
      </ol>

      <Dialog open={resolving} onOpenChange={setResolving}>
        <DialogContent className="sm:max-w-lg">
          <ResolveForm
            count={toResolve}
            pending={send.isPending}
            onResolve={(permission_mode, instructions) =>
              send.mutate(
                { action: "resolve", permission_mode, instructions },
                { onSuccess: () => setResolving(false), onError },
              )
            }
          />
        </DialogContent>
      </Dialog>
    </aside>
  )
}

interface CommentCardProps {
  item: Annotation
  attached: boolean
  focused: boolean
  onReveal: () => void
  onDismiss: () => void
}

function CommentCard({ item, attached, focused, onReveal, onDismiss }: CommentCardProps) {
  return (
    <article
      id={`comment-${item.id}`}
      aria-label={`${KIND_LABELS[item.kind]}: ${excerpt(item.quote, 60)}`}
      data-kind={item.kind}
      data-status={item.status}
      data-anchor={item.anchor_state}
      className={cn(
        "space-y-1.5 rounded-lg border bg-card p-3",
        focused ? "border-yellow-400 ring-2 ring-yellow-300/60" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className={cn("rounded-full border px-2 py-0.5 font-medium", KIND_STYLES[item.kind])}>
          {KIND_LABELS[item.kind]}
        </span>
        <span className="text-muted-foreground">{STATUS_LABELS[item.status]}</span>
        {!attached && (
          <span
            className="text-amber-800"
            title="The text was rewritten and this passage is not in it any more"
          >
            · passage no longer in the text
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onReveal}
        disabled={!attached}
        title={attached ? "Show the passage in the text" : undefined}
        className="block w-full border-l-2 border-border pl-2 text-left text-xs text-muted-foreground enabled:hover:text-foreground"
      >
        {excerpt(item.quote)}
      </button>
      {item.body && <p className="break-words whitespace-pre-line">{item.body}</p>}
      {item.status_reason && (
        <p role="alert" className="text-xs text-red-800">
          Not answered: {item.status_reason}
        </p>
      )}
      {item.response_markdown && (
        <div className="rounded-md bg-muted/60 px-2.5 py-2">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            {item.status === "declined" ? "Why the agent declined" : "The agent"}
          </p>
          <Markdown source={item.response_markdown} />
        </div>
      )}
      {item.status === "open" && (
        <div className="flex justify-end">
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Withdraw
          </Button>
        </div>
      )}
    </article>
  )
}

interface ResolveFormProps {
  count: number
  pending: boolean
  onResolve: (mode: PermissionMode, instructions: string | undefined) => void
}

/** Resolve changes files: what will happen is said before it is asked. */
function ResolveForm({ count, pending, onResolve }: ResolveFormProps) {
  const id = useId()
  const [mode, setMode] = useState<PermissionMode>("edit")
  const [instructions, setInstructions] = useState("")

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onResolve(mode, instructions.trim() || undefined)
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <DialogHeader>
        <DialogTitle>
          Resolve {count} change {count === 1 ? "request" : "requests"}
        </DialogTitle>
        <DialogDescription>
          The agent gets every open change request on this text in one turn. It edits the files
          of the project directly, as you; nothing is put aside for approval. Where requests
          conflict it decides, and it may decline a request and say why. What it changed is in
          Git afterwards.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-mode`} className="text-sm font-medium">
          What the agent may do
        </label>
        <NativeSelect
          id={`${id}-mode`}
          className="w-full"
          value={mode}
          onChange={(event) => setMode(event.target.value as PermissionMode)}
        >
          <NativeSelectOption value="edit">
            Edit files (commands it tries to run are refused)
          </NativeSelectOption>
          <NativeSelectOption value="full">
            Full autonomy (edit files and run commands, such as tests)
          </NativeSelectOption>
        </NativeSelect>
      </div>
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-instructions`} className="text-sm font-medium">
          Instructions for the agent{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Textarea
          id={`${id}-instructions`}
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          rows={2}
          maxLength={5000}
        />
      </div>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
        <Button type="submit" disabled={pending}>
          Resolve
        </Button>
      </DialogFooter>
    </form>
  )
}
