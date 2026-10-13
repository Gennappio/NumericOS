import { useRef } from "react"
import type { CommentTarget } from "@/api/client"
import { Clarification } from "@/components/comments/Clarification"
import { CommentsPanel } from "@/components/comments/CommentsPanel"
import { SelectionBar } from "@/components/comments/SelectionBar"
import { useCommenting } from "@/components/comments/useCommenting"
import { Markdown } from "@/components/markdown/Markdown"
import { cn } from "@/lib/utils"

interface CommentableProps {
  projectId: string
  target: CommentTarget
  /** The Markdown source, and which version of the text it is. */
  source: string
  version: number
  className?: string
  /** The box of the text: its look, and its name when it is a document of its own. */
  boxClassName?: string
  label?: string
  resolveImage?: (path: string) => string
  /** Where the comments are listed: beside the text (a document) or under it (an answer). */
  layout: "side" | "below"
  /** Why the agent cannot be asked now, if so; comments can still be written. */
  blocked: string | null
  supervisorAlive: boolean
  onError: (error: unknown) => void
}

/**
 * A text of the agent that can be commented. Select any passage: a small bar offers to ask
 * for a clarification, to request a change or to add a note. The passage is kept as a range
 * of the Markdown source, so a comment stays on its words. Comments are listed with two
 * buttons that send them to the agent together: Clarify and Resolve. A clarification the
 * agent gave is shown right after the paragraph of its passage; the text is not rewritten.
 */
export function Commentable({
  projectId,
  target,
  source,
  version,
  className,
  boxClassName,
  label,
  resolveImage,
  layout,
  blocked,
  supervisorAlive,
  onError,
}: CommentableProps) {
  const box = useRef<HTMLDivElement>(null)
  const commenting = useCommenting({ box, projectId, target, source, version, onError })
  const { draft } = commenting
  return (
    <div
      className={cn(
        layout === "side" && "grid gap-6 xl:grid-cols-[minmax(0,1fr)_21rem]",
        layout === "below" && "space-y-3",
      )}
    >
      <div
        ref={box}
        role={label ? "article" : undefined}
        aria-label={label}
        className={cn("relative min-w-0", boxClassName)}
        {...commenting.handlers}
        data-commentable={target.id}
      >
        <Markdown
          source={source}
          className={className}
          resolveImage={resolveImage}
          positions
          slots={commenting.slots}
          renderSlot={(ids) =>
            ids.map((id) => {
              const item = commenting.clarified.get(id)
              return item ? (
                <Clarification key={id} item={item} onFocus={() => commenting.focus(id)} />
              ) : null
            })
          }
        />
        {draft && (
          <SelectionBar
            draft={draft}
            quote={source.slice(draft.range.start, draft.range.end)}
            saving={commenting.saving}
            onChange={commenting.setDraft}
            onSave={commenting.save}
          />
        )}
      </div>

      <CommentsPanel
        projectId={projectId}
        target={target}
        annotations={commenting.annotations}
        current={commenting.sameVersion}
        pendingMessageId={commenting.pendingMessageId}
        pendingSessionId={commenting.pendingSessionId}
        focused={commenting.focused}
        layout={layout}
        blocked={blocked}
        supervisorAlive={supervisorAlive}
        onReveal={commenting.reveal}
        onError={onError}
      />
    </div>
  )
}
