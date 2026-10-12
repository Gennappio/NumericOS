import { useQueryClient } from "@tanstack/react-query"
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
} from "react"
import type { Annotation, AnnotationKind, CommentTarget } from "@/api/client"
import { queryKeys, useAnnotations, useCreateAnnotation } from "@/api/queries"
import { CommentsPanel } from "@/components/comments/CommentsPanel"
import { Markdown } from "@/components/markdown/Markdown"
import type { Slot } from "@/components/markdown/sourcePositions"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { excerpt, highlightName, KIND_ACTIONS, KIND_PROMPTS } from "@/lib/comments"
import { clearHighlights, setHighlights } from "@/lib/highlights"
import {
  fromCodePoints,
  offsetAtPoint,
  rangeToSource,
  sourceToRanges,
  toCodePoints,
  type SourceRange,
} from "@/lib/sourceMap"
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

interface Draft {
  range: SourceRange
  /** Where the bar goes, relative to the text's box. */
  top: number
  left: number
  kind: AnnotationKind | null
}

const KINDS: AnnotationKind[] = ["clarification", "change", "note"]

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
  const owner = useId()
  const queryClient = useQueryClient()
  const box = useRef<HTMLDivElement>(null)
  const listed = useAnnotations(projectId, target)
  const create = useCreateAnnotation(projectId, target)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [focused, setFocused] = useState<string | null>(null)

  // Comments of another version of the text have offsets that mean nothing here: they are
  // drawn only when the list and the text are of the same version.
  const current = listed.data?.target_version === version
  const annotations = useMemo(
    () => (listed.data?.annotations ?? []).filter((item) => item.status !== "dismissed"),
    [listed.data],
  )
  const attached = useMemo(
    () => (current ? annotations.filter((item) => item.anchor_state === "attached") : []),
    [annotations, current],
  )
  const rangeOf = useCallback(
    (item: Annotation): SourceRange => ({
      start: fromCodePoints(source, item.start_offset),
      end: fromCodePoints(source, item.end_offset),
    }),
    [source],
  )

  // A clarification the agent gave is shown after the block of its passage.
  const clarified = useMemo(
    () => attached.filter((item) => item.kind === "clarification" && item.response_markdown),
    [attached],
  )
  const slots: Slot[] = useMemo(
    () => clarified.map((item) => ({ id: item.id, after: rangeOf(item).end })),
    [clarified, rangeOf],
  )

  // The passages are highlighted on the page as it is rendered now.
  useLayoutEffect(() => {
    const root = box.current
    if (!root) return
    const groups: Record<string, Range[]> = {}
    for (const item of attached) {
      const name = item.id === focused ? "nos-focus" : highlightName(item)
      groups[name] = [...(groups[name] ?? []), ...sourceToRanges(root, rangeOf(item))]
    }
    if (draft) groups["nos-draft"] = sourceToRanges(root, draft.range)
    setHighlights(owner, groups)
  }, [attached, draft, focused, owner, rangeOf, slots])
  useEffect(() => () => clearHighlights(owner), [owner])

  // When the turn that was answering ends, the text itself may be another: a Resolve can
  // rewrite a document and change files. Everything of the project is read again once.
  const pending = listed.data?.pending_message_id ?? null
  const wasPending = useRef<string | null>(null)
  useEffect(() => {
    if (wasPending.current && !pending) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
    }
    wasPending.current = pending
  }, [pending, projectId, queryClient])

  /** A selection inside the text becomes a draft; the bar appears under its end. */
  function selectionChanged() {
    const root = box.current
    const selection = window.getSelection()
    if (!root || !selection || selection.rangeCount === 0 || selection.isCollapsed) return
    const range = selection.getRangeAt(0)
    if (!root.contains(range.commonAncestorContainer)) return
    const found = rangeToSource(root, range)
    if (!found) return
    const rects = range.getClientRects?.() ?? []
    const last = rects.length > 0 ? rects[rects.length - 1] : range.getBoundingClientRect?.()
    const frame = root.getBoundingClientRect()
    setDraft({
      range: found,
      top: (last?.bottom ?? frame.top) - frame.top + 6,
      left: Math.max(0, Math.min((last?.left ?? frame.left) - frame.left, frame.width - 280)),
      kind: null,
    })
  }

  /** A click on a highlighted passage brings its comment forward. */
  function clicked(event: MouseEvent) {
    const root = box.current
    if (!root || !window.getSelection()?.isCollapsed) return
    const offset = offsetAtPoint(root, event.clientX, event.clientY)
    if (offset === null) return
    const hit = attached.find((item) => {
      const range = rangeOf(item)
      return offset >= range.start && offset < range.end
    })
    if (hit) focus(hit.id)
  }

  function focus(id: string) {
    setFocused(id)
    document.getElementById(`comment-${id}`)?.scrollIntoView?.({ block: "nearest" })
  }

  /** From the list to the text: the passage of a comment is shown and marked. */
  function reveal(item: Annotation) {
    setFocused(item.id)
    const root = box.current
    if (!root || item.anchor_state !== "attached" || !current) return
    const [range] = sourceToRanges(root, rangeOf(item))
    const start = range?.startContainer
    const element = start instanceof Element ? start : start?.parentElement
    element?.scrollIntoView?.({ block: "center", behavior: "smooth" })
  }

  function save(body: string) {
    if (!draft?.kind) return
    create.mutate(
      {
        kind: draft.kind,
        body,
        quote: source.slice(draft.range.start, draft.range.end),
        start_offset: toCodePoints(source, draft.range.start),
        end_offset: toCodePoints(source, draft.range.end),
      },
      {
        onSuccess: (made) => {
          setDraft(null)
          setFocused(made.id)
          window.getSelection()?.removeAllRanges()
        },
        onError,
      },
    )
  }

  const byId = new Map(clarified.map((item) => [item.id, item]))
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
        onMouseUp={selectionChanged}
        onKeyUp={selectionChanged}
        onClick={clicked}
        data-commentable={target.id}
      >
        <Markdown
          source={source}
          className={className}
          resolveImage={resolveImage}
          positions
          slots={slots}
          renderSlot={(ids) =>
            ids.map((id) => {
              const item = byId.get(id)
              return item ? <Clarification key={id} item={item} onFocus={() => focus(id)} /> : null
            })
          }
        />
        {draft && (
          <div
            role="dialog"
            aria-label="Comment on the selected passage"
            className="absolute z-20 w-[min(22rem,100%)] rounded-lg border border-border bg-popover p-2 font-sans text-sm shadow-lg"
            style={{ top: draft.top, left: draft.left }}
            // The selection must survive a press on the bar: only a click acts.
            onMouseDown={(event) => {
              if (!(event.target instanceof HTMLTextAreaElement)) event.preventDefault()
            }}
            onMouseUp={(event) => event.stopPropagation()}
            onKeyUp={(event) => event.stopPropagation()}
            onClick={(event) => event.stopPropagation()}
          >
            {draft.kind === null ? (
              <div className="flex flex-wrap gap-1">
                {KINDS.map((kind) => (
                  <Button
                    key={kind}
                    size="sm"
                    variant={kind === "note" ? "ghost" : "outline"}
                    onClick={() => setDraft({ ...draft, kind })}
                  >
                    {KIND_ACTIONS[kind]}
                  </Button>
                ))}
                <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <DraftForm
                kind={draft.kind}
                quote={source.slice(draft.range.start, draft.range.end)}
                saving={create.isPending}
                onSave={save}
                onCancel={() => setDraft(null)}
              />
            )}
          </div>
        )}
      </div>

      <CommentsPanel
        projectId={projectId}
        target={target}
        annotations={annotations}
        current={current}
        pendingMessageId={pending}
        pendingSessionId={listed.data?.pending_session_id ?? null}
        focused={focused}
        layout={layout}
        blocked={blocked}
        supervisorAlive={supervisorAlive}
        onReveal={reveal}
        onError={onError}
      />
    </div>
  )
}

/** What the agent answered about a passage, right after the paragraph the passage is in. */
function Clarification({ item, onFocus }: { item: Annotation; onFocus: () => void }) {
  return (
    <aside className="clarification" aria-label={`Clarification of: ${excerpt(item.quote, 60)}`}>
      <details open>
        <summary className="cursor-pointer text-xs font-medium text-sky-900" onClick={onFocus}>
          Clarification <span className="font-normal text-sky-900/80">· {item.body}</span>
        </summary>
        <div className="mt-1.5">
          <Markdown source={item.response_markdown ?? ""} />
        </div>
      </details>
    </aside>
  )
}

interface DraftFormProps {
  kind: AnnotationKind
  quote: string
  saving: boolean
  onSave: (body: string) => void
  onCancel: () => void
}

function DraftForm({ kind, quote, saving, onSave, onCancel }: DraftFormProps) {
  const id = useId()
  const [body, setBody] = useState("")
  const needsText = kind !== "note"

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (needsText && !body.trim()) return
    onSave(body.trim())
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.currentTarget.form?.requestSubmit()
    }
    if (event.key === "Escape") onCancel()
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <p className="line-clamp-2 border-l-2 border-border pl-2 text-xs text-muted-foreground">
        {excerpt(quote, 160)}
      </p>
      <label htmlFor={`${id}-body`} className="text-xs font-medium">
        {KIND_PROMPTS[kind]}
      </label>
      <Textarea
        id={`${id}-body`}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        onKeyDown={keyDown}
        rows={3}
        maxLength={5000}
        autoFocus
      />
      <div className="flex justify-end gap-1">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={saving || (needsText && !body.trim())}>
          {KIND_ACTIONS[kind]}
        </Button>
      </div>
    </form>
  )
}
