import { ArrowRightIcon } from "lucide-react"
import type { DocumentOut, Pipeline, PipelineNode } from "@/api/client"
import { Markdown } from "@/components/markdown/Markdown"
import { PipelineBox } from "@/components/pipeline/PipelineBox"
import type { DrawnBoard } from "@/lib/export/board"
import { KIND_LABELS, sections } from "@/lib/pipeline"

interface ExportPipelineProps {
  document: DocumentOut
  pipeline: Pipeline
  resolveImage: (path: string) => string
  /**
   * The board once its boxes were measured and placed. Without it the boxes are only laid
   * out one after the other, each at its own size: the pass in which they are measured.
   */
  board: DrawnBoard | null
}

const ARROW = "#94a3b8"
const NO_SLOTS = () => null

/**
 * The pipeline as a still page: the title and summary, the board with every box and arrow
 * where it stands, and the arrows in words. On paper a board that wide would be cut, so a
 * printed copy shows the boxes one under the other instead, in the order of a run.
 */
export function ExportPipeline({ document, pipeline, resolveImage, board }: ExportPipelineProps) {
  const source = document.markdown
  const parts = sections(source, pipeline)
  const titles = new Map(pipeline.nodes.map((node) => [node.id, node.title]))
  const box = (node: PipelineNode) => {
    const part = parts.boxes.get(node.id)!
    return (
      <PipelineBox
        node={node}
        source={source.slice(part.start, part.end)}
        offset={0}
        slots={[]}
        renderSlot={NO_SLOTS}
        changed={[]}
        resolveImage={resolveImage}
        still
      />
    )
  }
  const placed = new Map(board?.boxes.map((rect) => [rect.id, rect]))

  return (
    <div className="space-y-4">
      <Markdown
        source={source.slice(parts.header.start, parts.header.end)}
        className="pipeline-header"
        resolveImage={resolveImage}
      />

      <div className="export-screen-only overflow-x-auto rounded-lg border border-border bg-slate-50">
        {board ? (
          <div
            className="export-board relative"
            style={{ width: board.width, height: board.height }}
          >
            <svg
              aria-hidden="true"
              className="absolute inset-0"
              width={board.width}
              height={board.height}
              style={{ overflow: "visible" }}
            >
              <defs>
                <marker
                  id="export-arrowhead"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="9"
                  markerHeight="9"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={ARROW} />
                </marker>
              </defs>
              {board.arrows.map((arrow) => (
                <path
                  key={arrow.key}
                  d={arrow.path}
                  fill="none"
                  stroke={ARROW}
                  strokeWidth={1.75}
                  strokeDasharray={arrow.back ? "6 4" : undefined}
                  markerEnd="url(#export-arrowhead)"
                />
              ))}
            </svg>
            {pipeline.nodes.map((node) => {
              const rect = placed.get(node.id)
              return (
                <div
                  key={node.id}
                  className="absolute"
                  style={{ left: rect?.x ?? 0, top: rect?.y ?? 0 }}
                >
                  {box(node)}
                </div>
              )
            })}
            {board.arrows
              .filter((arrow) => arrow.label)
              .map((arrow) => (
                <div
                  key={arrow.key}
                  className="pipeline-arrow-label"
                  style={{
                    left: arrow.labelX,
                    top: arrow.labelY,
                    transform: "translate(-50%, -50%)",
                  }}
                >
                  {arrow.label}
                </div>
              ))}
          </div>
        ) : (
          // Measured here: side by side, each box as tall as its text makes it.
          <div className="flex flex-wrap items-start gap-6 p-6">
            {pipeline.nodes.map((node) => (
              <div key={node.id}>{box(node)}</div>
            ))}
          </div>
        )}
      </div>

      <ol className="export-print-only space-y-4" aria-label="The parts, in the order of a run">
        {pipeline.nodes.map((node) => {
          const part = parts.boxes.get(node.id)!
          return (
            <li key={node.id} className="export-part">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {KIND_LABELS[node.kind]}
                {node.repeats && <> · repeats: {node.repeats}</>}
              </p>
              <Markdown
                source={source.slice(part.start, part.end)}
                className="pipeline-note"
                resolveImage={resolveImage}
              />
              {node.files.length > 0 && (
                <p className="mt-1 font-mono text-xs break-all text-muted-foreground">
                  {node.files.join(", ")}
                </p>
              )}
            </li>
          )
        })}
      </ol>

      {pipeline.edges.length > 0 && (
        <section>
          <h2 className="text-sm font-medium">The arrows</h2>
          <ul aria-label="Arrows of the pipeline" className="mt-2 space-y-1 text-sm">
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
        </section>
      )}
    </div>
  )
}
