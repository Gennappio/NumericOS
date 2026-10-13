import { useQueryClient } from "@tanstack/react-query"
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type RefObject,
} from "react"
import type { Annotation, AnnotationKind, CommentTarget } from "@/api/client"
import { queryKeys, useAnnotations, useCreateAnnotation } from "@/api/queries"
import type { Slot } from "@/components/markdown/sourcePositions"
import { highlightName } from "@/lib/comments"
import { clearHighlights, setHighlights } from "@/lib/highlights"
import {
  fromCodePoints,
  offsetAtPoint,
  rangeToSource,
  sourceToRanges,
  toCodePoints,
  type SourceRange,
} from "@/lib/sourceMap"

export interface Draft {
  range: SourceRange
  /** Where the bar goes, relative to the box of the text. */
  top: number
  left: number
  kind: AnnotationKind | null
}

interface CommentingOptions {
  /**
   * The element that holds the whole text, however many pieces it is drawn in. It is the
   * caller's own ref, given here and never handed back: the linter takes anything a ref
   * comes out of for a ref, and would then object to every other value read from it.
   */
  box: RefObject<HTMLDivElement | null>
  projectId: string
  target: CommentTarget
  /** The Markdown source, and which version of the text it is. */
  source: string
  version: number
  /**
   * The text is drawn by something that puts its pieces on the page in its own time (the
   * boxes of a board): the highlights are drawn again whenever the page under the box changes.
   */
  watch?: boolean
  /** Whether a selection may be commented; one that spans two boxes of a board may not. */
  accepts?: (range: SourceRange) => boolean
  /** Bring a passage into view. Without it the page scrolls to the passage. */
  onReveal?: (range: SourceRange) => void
  onError: (error: unknown) => void
}

export interface Commenting {
  /** What the box listens to: a selection that ends, a click on a highlighted passage. */
  handlers: {
    onMouseUp: () => void
    onKeyUp: () => void
    onClick: (event: MouseEvent) => void
  }
  /** The comments of the text, without the withdrawn ones. */
  annotations: Annotation[]
  /** The list is of the version of the text on the page. */
  sameVersion: boolean
  /** Clarifications the agent gave, by the id of their comment. */
  clarified: Map<string, Annotation>
  /** Where each of them is shown: after the block of its passage (source offsets, UTF-16). */
  slots: Slot[]
  draft: Draft | null
  setDraft: (draft: Draft | null) => void
  saving: boolean
  save: (body: string) => void
  focused: string | null
  focus: (id: string) => void
  reveal: (item: Annotation) => void
  pendingMessageId: string | null
  pendingSessionId: string | null
}

/**
 * What makes a text of the agent commentable, whatever draws it: the comments of the text,
 * their highlights on the page, the selection that becomes a new comment. The text must be
 * rendered inside `box` with the marks of its source (`Markdown` with `positions`); a passage
 * is kept as a range of the Markdown source, so a comment stays on its words.
 */
export function useCommenting({
  box,
  projectId,
  target,
  source,
  version,
  watch = false,
  accepts,
  onReveal,
  onError,
}: CommentingOptions): Commenting {
  const owner = useId()
  const queryClient = useQueryClient()
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
    () =>
      new Map(
        attached
          .filter((item) => item.kind === "clarification" && item.response_markdown)
          .map((item) => [item.id, item]),
      ),
    [attached],
  )
  const slots: Slot[] = useMemo(
    () => [...clarified.values()].map((item) => ({ id: item.id, after: rangeOf(item).end })),
    [clarified, rangeOf],
  )

  // The passages are highlighted on the page as it is rendered now. The places of the
  // clarifications move the text: it is highlighted again when they change.
  const redraw = useRef(() => {})
  useLayoutEffect(() => {
    function draw() {
      const root = box.current
      if (!root) return
      const groups: Record<string, Range[]> = {}
      for (const item of attached) {
        const name = item.id === focused ? "nos-focus" : highlightName(item)
        groups[name] = [...(groups[name] ?? []), ...sourceToRanges(root, rangeOf(item))]
      }
      if (draft) groups["nos-draft"] = sourceToRanges(root, draft.range)
      setHighlights(owner, groups)
    }
    redraw.current = draw
    draw()
  }, [attached, box, draft, focused, owner, rangeOf, slots])
  useEffect(() => () => clearHighlights(owner), [owner])
  useEffect(() => {
    const root = box.current
    if (!watch || !root) return
    // Drawing a highlight does not change the page, so this cannot feed itself.
    let frame = 0
    const observer = new MutationObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => redraw.current())
    })
    observer.observe(root, { childList: true, subtree: true, characterData: true })
    return () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [box, watch])

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
    if (!found || (accepts && !accepts(found))) return
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

  const focus = useCallback((id: string) => {
    setFocused(id)
    document.getElementById(`comment-${id}`)?.scrollIntoView?.({ block: "nearest" })
  }, [])

  /** From the list to the text: the passage of a comment is shown and marked. */
  function reveal(item: Annotation) {
    setFocused(item.id)
    const root = box.current
    if (!root || item.anchor_state !== "attached" || !current) return
    if (onReveal) {
      onReveal(rangeOf(item))
      return
    }
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

  return {
    handlers: { onMouseUp: selectionChanged, onKeyUp: selectionChanged, onClick: clicked },
    annotations,
    sameVersion: current,
    clarified,
    slots,
    draft,
    setDraft,
    saving: create.isPending,
    save,
    focused,
    focus,
    reveal,
    pendingMessageId: pending,
    pendingSessionId: listed.data?.pending_session_id ?? null,
  }
}
