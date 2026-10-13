import type { Pipeline, PipelineNodeKind } from "@/api/client"
import { fromCodePoints, type SourceRange } from "@/lib/sourceMap"

// `Record` over the generated union: a kind added to the contract is a compile error here
// until it has a label and a colour.

/** What a box is in one run of the program. */
export const KIND_LABELS: Record<PipelineNodeKind, string> = {
  input: "Input",
  process: "Stage",
  output: "Output",
  external: "External",
}

export const KIND_HINTS: Record<PipelineNodeKind, string> = {
  input: "Something the program reads",
  process: "A stage of the computation",
  output: "Something the program writes",
  external: "Work done outside the project's own code",
}

/**
 * A colour per kind of box, as notes of different colours on a board: the paper of the note,
 * the bar it is dragged by, and its tag.
 */
export const KIND_STYLES: Record<PipelineNodeKind, { note: string; bar: string; tag: string }> = {
  input: {
    note: "border-sky-300 bg-sky-50",
    bar: "bg-sky-200/80 text-sky-950",
    tag: "bg-sky-600 text-white",
  },
  process: {
    note: "border-amber-300 bg-amber-50",
    bar: "bg-amber-200/80 text-amber-950",
    tag: "bg-amber-500 text-white",
  },
  output: {
    note: "border-emerald-300 bg-emerald-50",
    bar: "bg-emerald-200/80 text-emerald-950",
    tag: "bg-emerald-600 text-white",
  },
  external: {
    note: "border-violet-300 bg-violet-50",
    bar: "bg-violet-200/80 text-violet-950",
    tag: "bg-violet-600 text-white",
  },
}

/** The same colours where only a colour can be given (the small map of the board). */
export const KIND_COLORS: Record<PipelineNodeKind, string> = {
  input: "#7dd3fc",
  process: "#fcd34d",
  output: "#6ee7b7",
  external: "#c4b5fd",
}

export const KINDS = Object.keys(KIND_LABELS) as PipelineNodeKind[]

export interface Sections {
  /** The title and the summary: what is before the first box. */
  header: SourceRange
  /** The section of each box, by the id of the box. */
  boxes: Map<string, SourceRange>
}

/**
 * Where each part of a pipeline is in its text, in UTF-16 units (as JavaScript indexes
 * strings; the API counts Unicode code points). Every box is a section of the one text that
 * comments are attached to.
 */
export function sections(markdown: string, pipeline: Pipeline): Sections {
  const boxes = new Map<string, SourceRange>()
  for (const node of pipeline.nodes) {
    boxes.set(node.id, {
      start: fromCodePoints(markdown, node.start),
      end: fromCodePoints(markdown, node.end),
    })
  }
  const first = Math.min(markdown.length, ...[...boxes.values()].map((range) => range.start))
  return { header: { start: 0, end: markdown.slice(0, first).trimEnd().length }, boxes }
}

/** The part a range of the text lies in: "header", the id of a box, or null for none. */
export function partOf(parts: Sections, range: SourceRange): string | null {
  const inside = (part: SourceRange) => range.start >= part.start && range.end <= part.end
  if (inside(parts.header)) return "header"
  for (const [id, part] of parts.boxes) if (inside(part)) return id
  return null
}
