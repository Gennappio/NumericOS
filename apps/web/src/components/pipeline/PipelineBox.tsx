import {
  ArrowDownToLineIcon,
  ArrowUpFromLineIcon,
  CogIcon,
  GripHorizontalIcon,
  PackageIcon,
  RepeatIcon,
  type LucideIcon,
} from "lucide-react"
import type { ReactNode } from "react"
import type { PipelineNode, PipelineNodeKind } from "@/api/client"
import { Markdown } from "@/components/markdown/Markdown"
import type { Slot } from "@/components/markdown/sourcePositions"
import { KIND_HINTS, KIND_LABELS, KIND_STYLES } from "@/lib/pipeline"
import { cn } from "@/lib/utils"

const KIND_ICONS: Record<PipelineNodeKind, LucideIcon> = {
  input: ArrowDownToLineIcon,
  process: CogIcon,
  output: ArrowUpFromLineIcon,
  external: PackageIcon,
}

/** The class of the bar a box is dragged by; the board looks for it. */
export const DRAG_HANDLE = "pipeline-drag"

interface PipelineBoxProps {
  node: PipelineNode
  /** The section of the box in the text of the pipeline: its title, then its description. */
  source: string
  /** Where that section starts in the text (UTF-16): comments count from the start of it. */
  offset: number
  /** Clarifications shown inside the box, placed relative to the section. */
  slots: Slot[]
  renderSlot: (ids: string[]) => ReactNode
  /** The files of the box that changed since the pipeline was written. */
  changed: string[]
  resolveImage?: (path: string) => string
  /**
   * On a page where nothing moves and nothing is commented (a shared copy): the bar is not a
   * handle, and the text carries no marks of where it comes from.
   */
  still?: boolean
}

/**
 * One part of the program, as a note on the board: what kind of part it is, its title, its
 * description and the files it is in. The bar at the top moves the note; everything under it
 * is text that can be selected and commented.
 */
export function PipelineBox({
  node,
  source,
  offset,
  slots,
  renderSlot,
  changed,
  resolveImage,
  still = false,
}: PipelineBoxProps) {
  const styles = KIND_STYLES[node.kind]
  const Icon = KIND_ICONS[node.kind]
  const stale = new Set(changed)
  return (
    <article
      aria-label={node.title}
      data-node={node.id}
      data-kind={node.kind}
      data-changed={changed.length > 0}
      className={cn(
        "w-80 rounded-lg border shadow-md",
        styles.note,
        changed.length > 0 && "ring-2 ring-amber-400 ring-offset-1",
      )}
    >
      <header
        className={cn(
          "flex items-center gap-2 rounded-t-[0.45rem] px-3 py-1.5 text-xs",
          !still && [DRAG_HANDLE, "cursor-grab active:cursor-grabbing"],
          styles.bar,
        )}
        title={still ? undefined : "Drag to move this box"}
      >
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium",
            styles.tag,
          )}
          title={KIND_HINTS[node.kind]}
        >
          <Icon aria-hidden="true" className="size-3" />
          {KIND_LABELS[node.kind]}
        </span>
        {node.repeats && (
          <span className="inline-flex min-w-0 items-center gap-1" title="This part repeats">
            <RepeatIcon aria-hidden="true" className="size-3 shrink-0" />
            <span className="truncate">{node.repeats}</span>
          </span>
        )}
        {!still && (
          <GripHorizontalIcon aria-hidden="true" className="ml-auto size-4 shrink-0 opacity-60" />
        )}
      </header>

      {/* Not a handle: a press here starts a selection of the text, not a move of the box. */}
      <div className={cn("px-3 pt-2 pb-3", !still && "pipeline-text nodrag")}>
        <Markdown
          source={source}
          className="pipeline-note"
          resolveImage={resolveImage}
          positions={!still}
          offset={offset}
          slots={slots}
          renderSlot={renderSlot}
        />
      </div>

      {node.files.length > 0 && (
        <footer className="space-y-1 border-t border-black/10 px-3 py-2">
          {changed.length > 0 && (
            <p role="status" className="text-xs font-medium text-amber-900">
              The code of this part changed since this was written.
            </p>
          )}
          <ul aria-label={`Files of ${node.title}`} className="flex flex-wrap gap-1">
            {node.files.map((path) => (
              <li
                key={path}
                title={stale.has(path) ? `${path} (changed since)` : path}
                className={cn(
                  "max-w-full truncate rounded border px-1.5 py-0.5 font-mono text-[0.6875rem]",
                  stale.has(path)
                    ? "border-amber-400 bg-amber-100 text-amber-950"
                    : "border-black/10 bg-white/70 text-slate-700",
                )}
              >
                {path.split("/").pop()}
              </li>
            ))}
          </ul>
        </footer>
      )}
    </article>
  )
}
