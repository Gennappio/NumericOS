import { ArrowRightIcon, LayoutGridIcon, MessagesSquareIcon } from "lucide-react"
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react"
import { fileContentUrl, type DocumentOut, type Pipeline } from "@/api/client"
import { Clarification } from "@/components/comments/Clarification"
import { CommentsPanel } from "@/components/comments/CommentsPanel"
import { SelectionBar } from "@/components/comments/SelectionBar"
import { useCommenting } from "@/components/comments/useCommenting"
import { Markdown } from "@/components/markdown/Markdown"
import type { Slot } from "@/components/markdown/sourcePositions"
import { PipelineBox } from "@/components/pipeline/PipelineBox"
import { PipelineCanvas, type CanvasHandle } from "@/components/pipeline/PipelineCanvas"
import { Button } from "@/components/ui/button"
import { countOpen } from "@/lib/comments"
import { partOf, sections } from "@/lib/pipeline"
import type { SourceRange } from "@/lib/sourceMap"

interface PipelineBoardProps {
  projectId: string
  /** A pipeline that was written: its text and its boxes and arrows. */
  document: DocumentOut
  pipeline: Pipeline
  /** Why the agent cannot be asked now, if so; comments can still be written. */
  blocked: string | null
  supervisorAlive: boolean
  onError: (error: unknown) => void
}

/**
 * The pipeline of a project as a board: every part of the program is a box with its
 * description, and arrows say what passes from one part to the next. The boxes are sections
 * of one text, so any passage of any box is commented as in every other text of the agent:
 * select it, then ask for a clarification, request a change or add a note. Clarify and
 * Resolve send the requests of the whole board together.
 */
export function PipelineBoard({
  projectId,
  document,
  pipeline,
  blocked,
  supervisorAlive,
  onError,
}: PipelineBoardProps) {
  const source = document.markdown
  const parts = useMemo(() => sections(source, pipeline), [source, pipeline])
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<CanvasHandle>(null)
  const header = useRef<HTMLDivElement>(null)
  const target = useMemo(() => ({ type: "document" as const, id: document.id }), [document.id])
  const commenting = useCommenting({
    box,
    projectId,
    target,
    source,
    version: document.version,
    // The board puts its boxes on the page in its own time.
    watch: true,
    // A passage belongs to one box (or to the summary): a comment is about one part.
    accepts: (range) => partOf(parts, range) !== null,
    onReveal: (range) => {
      const part = partOf(parts, range)
      if (part === "header") header.current?.scrollIntoView?.({ block: "nearest" })
      else if (part) {
        // On a narrow page the list is under the board: the board comes back into view.
        box.current?.scrollIntoView?.({ block: "nearest" })
        canvas.current?.show(part)
      }
    },
    onError,
  })
  const { draft, clarified, focus } = commenting
  // The list of comments opens with the first comment; after that it is as it was left.
  const [listOpen, setListOpen] = useState<boolean | null>(null)
  const open = listOpen ?? commenting.annotations.length > 0

  const renderSlot = useCallback(
    (ids: string[]): ReactNode =>
      ids.map((id) => {
        const item = clarified.get(id)
        return item ? <Clarification key={id} item={item} onFocus={() => focus(id)} /> : null
      }),
    [clarified, focus],
  )
  /** The clarifications shown inside a part, placed from the start of that part. */
  const slotsOf = useCallback(
    (part: SourceRange): Slot[] =>
      commenting.slots
        .filter((slot) => slot.after > part.start && slot.after <= part.end)
        .map((slot) => ({ id: slot.id, after: slot.after - part.start })),
    [commenting.slots],
  )
  const boxes = useMemo(() => {
    const changed = new Set(document.changed_sources ?? [])
    return new Map(
      pipeline.nodes.map((node) => {
        const part = parts.boxes.get(node.id)!
        return [
          node.id,
          <PipelineBox
            key={node.id}
            node={node}
            source={source.slice(part.start, part.end)}
            offset={part.start}
            slots={slotsOf(part)}
            renderSlot={renderSlot}
            changed={node.files.filter((path) => changed.has(path))}
            resolveImage={(path) => fileContentUrl(projectId, path)}
          />,
        ]
      }),
    )
  }, [document.changed_sources, pipeline.nodes, parts, source, slotsOf, renderSlot, projectId])
  const renderBox = useCallback((id: string) => boxes.get(id) ?? null, [boxes])
  const canvasNodes = useMemo(
    () => pipeline.nodes.map(({ id, kind, title }) => ({ id, kind, title })),
    [pipeline.nodes],
  )
  const titles = new Map(pipeline.nodes.map((node) => [node.id, node.title]))
  const waiting =
    countOpen(commenting.annotations, "clarification") + countOpen(commenting.annotations, "change")

  return (
    <div className="space-y-2">
      {/* The list of comments is beside the board where the page is wide, under it elsewhere. */}
      <div className="flex flex-col rounded-lg border border-border bg-card xl:h-[78vh] xl:min-h-[36rem] xl:flex-row">
        <div
          ref={box}
          className="relative flex min-w-0 flex-1 flex-col"
          {...commenting.handlers}
          data-commentable={document.id}
        >
          <div ref={header} className="border-b border-border px-4 py-3">
            <Markdown
              source={source.slice(parts.header.start, parts.header.end)}
              className="pipeline-header"
              positions
              offset={parts.header.start}
              slots={slotsOf(parts.header)}
              renderSlot={renderSlot}
            />
          </div>
          <div className="relative h-[70vh] min-h-[28rem] xl:h-auto xl:min-h-0 xl:flex-1">
            <div className="absolute inset-0 overflow-hidden rounded-bl-lg bg-slate-50">
              <PipelineCanvas
                ref={canvas}
                documentId={document.id}
                version={document.version}
                nodes={canvasNodes}
                edges={pipeline.edges}
                renderBox={renderBox}
              />
            </div>
            <div className="absolute top-2 right-2 z-10 flex gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="bg-background shadow-sm"
                title="Put every box back in the order of a run"
                onClick={() => canvas.current?.tidy()}
              >
                <LayoutGridIcon data-icon="inline-start" />
                Tidy up
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="bg-background shadow-sm"
                aria-expanded={open}
                title={open ? "Hide the list of comments" : "Show the list of comments"}
                onClick={() => setListOpen(!open)}
              >
                <MessagesSquareIcon data-icon="inline-start" />
                Comments {commenting.annotations.length}
                {waiting > 0 && !open && <span className="text-orange-700">· {waiting} to send</span>}
              </Button>
            </div>
          </div>
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

        {open && (
          <div className="max-h-[26rem] overflow-y-auto border-t border-border p-3 xl:max-h-none xl:w-80 xl:shrink-0 xl:border-t-0 xl:border-l">
            <CommentsPanel
              projectId={projectId}
              target={target}
              annotations={commenting.annotations}
              current={commenting.sameVersion}
              pendingMessageId={commenting.pendingMessageId}
              pendingSessionId={commenting.pendingSessionId}
              focused={commenting.focused}
              layout="panel"
              blocked={blocked}
              supervisorAlive={supervisorAlive}
              onReveal={commenting.reveal}
              onError={onError}
            />
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Select any text of a box to comment it. Drag a box by its coloured bar. Scroll to move
        around the board; pinch, or hold Ctrl or ⌘ while scrolling, to zoom.
      </p>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">
          The arrows as a list ({pipeline.edges.length})
        </summary>
        {pipeline.edges.length === 0 ? (
          <p className="mt-2 text-muted-foreground">The agent drew no arrow between the boxes.</p>
        ) : (
          <ul aria-label="Arrows of the pipeline" className="mt-2 space-y-1">
            {pipeline.edges.map((edge) => (
              <li
                key={`${edge.source}->${edge.target}`}
                className="flex flex-wrap items-center gap-1.5"
              >
                <span className="font-medium">{titles.get(edge.source)}</span>
                <ArrowRightIcon aria-label="to" className="size-3.5 text-muted-foreground" />
                <span className="font-medium">{titles.get(edge.target)}</span>
                {edge.label && <span className="text-muted-foreground">· {edge.label}</span>}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  )
}
