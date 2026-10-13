import { getSmoothStepPath, Position } from "@xyflow/react"
import type { PipelineEdge } from "@/api/client"
import type { Positions, Sized } from "@/components/pipeline/layout"

export interface BoxRect extends Sized {
  x: number
  y: number
}

export interface DrawnArrow {
  key: string
  /** The line, as the `d` of an SVG path, from the right of one box to the left of another. */
  path: string
  /** Where its words go: the middle of the line. */
  labelX: number
  labelY: number
  label: string
  /** It points back to a box that comes before: it closes a loop, and is drawn dashed. */
  back: boolean
}

export interface DrawnBoard {
  width: number
  height: number
  boxes: BoxRect[]
  arrows: DrawnArrow[]
}

/**
 * A board as a still drawing: every box where it was placed, measured from the top left of
 * the drawing with a margin around, and every arrow as a line between the boxes it joins.
 * The same line the live board draws; here nothing moves, so it is computed once.
 */
export function drawBoard(
  sizes: Sized[],
  positions: Positions,
  edges: PipelineEdge[],
  margin = 48,
): DrawnBoard {
  const placed = sizes.map((size) => ({ ...size, ...(positions[size.id] ?? { x: 0, y: 0 }) }))
  if (placed.length === 0) return { width: 0, height: 0, boxes: [], arrows: [] }
  const left = Math.min(...placed.map((box) => box.x))
  const top = Math.min(...placed.map((box) => box.y))
  const boxes = placed.map((box) => ({
    ...box,
    x: Math.round(box.x - left + margin),
    y: Math.round(box.y - top + margin),
  }))
  const byId = new Map(boxes.map((box) => [box.id, box]))
  const arrows = edges.flatMap((edge) => {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) return []
    const [path, labelX, labelY] = getSmoothStepPath({
      sourceX: source.x + source.width,
      sourceY: source.y + source.height / 2,
      sourcePosition: Position.Right,
      targetX: target.x,
      targetY: target.y + target.height / 2,
      targetPosition: Position.Left,
      borderRadius: 12,
    })
    return [
      {
        key: `${edge.source}->${edge.target}`,
        path,
        labelX,
        labelY,
        label: edge.label,
        back: target.x < source.x,
      },
    ]
  })
  return {
    width: Math.max(...boxes.map((box) => box.x + box.width)) + margin,
    height: Math.max(...boxes.map((box) => box.y + box.height)) + margin,
    boxes,
    arrows,
  }
}
