import { Graph, layout } from "@dagrejs/dagre"

export interface Sized {
  id: string
  width: number
  height: number
}

export interface Arrow {
  source: string
  target: string
}

export type Positions = Record<string, { x: number; y: number }>

/** Room between two boxes one above the other, and between one box and the next. */
const GAP = { above: 56, across: 150 }

/**
 * Where the boxes of a pipeline go when nobody placed them: from left to right in the order
 * of a run, each arrow pointing forward where it can (an arrow that closes a loop points
 * back). Boxes that no arrow reaches are put in the order they were written in.
 */
export function layoutPipeline(nodes: Sized[], arrows: Arrow[]): Positions {
  const known = new Set(nodes.map((node) => node.id))
  const drawn = arrows.filter((arrow) => known.has(arrow.source) && known.has(arrow.target))
  // Without any arrow the order of the boxes is all there is: they follow one another.
  const links =
    drawn.length > 0
      ? drawn
      : nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id }))
  const graph = new Graph()
  graph.setGraph({ rankdir: "LR", nodesep: GAP.above, ranksep: GAP.across, marginx: 0, marginy: 0 })
  graph.setDefaultEdgeLabel(() => ({}))
  for (const node of nodes) graph.setNode(node.id, { width: node.width, height: node.height })
  for (const link of links) graph.setEdge(link.source, link.target)
  layout(graph)
  return Object.fromEntries(
    nodes.map((node) => {
      const centre = graph.node(node.id)
      return [node.id, { x: centre.x - node.width / 2, y: centre.y - node.height / 2 }]
    }),
  )
}

export interface Viewport {
  x: number
  y: number
  zoom: number
}

/** Under this zoom the text of a box is too small to read at a glance. */
export const READABLE_ZOOM = 0.85

/**
 * How a board is first shown: all of it when that leaves the text readable, and otherwise
 * its beginning at full size, with the rest a scroll away. A board is for reading the boxes
 * before it is for seeing them all.
 */
export function startViewport(
  nodes: (Sized & { x: number; y: number })[],
  width: number,
  height: number,
  padding = 32,
): Viewport {
  if (nodes.length === 0 || width <= 0 || height <= 0) return { x: 0, y: 0, zoom: 1 }
  const left = Math.min(...nodes.map((node) => node.x))
  const top = Math.min(...nodes.map((node) => node.y))
  const right = Math.max(...nodes.map((node) => node.x + node.width))
  const bottom = Math.max(...nodes.map((node) => node.y + node.height))
  const fit = Math.min(
    (width - 2 * padding) / (right - left),
    (height - 2 * padding) / (bottom - top),
  )
  const zoom = fit >= READABLE_ZOOM ? Math.min(1, fit) : 1
  const place = (from: number, to: number, room: number) =>
    (to - from) * zoom <= room - 2 * padding
      ? (room - (to - from) * zoom) / 2 - from * zoom // it fits: in the middle
      : padding - from * zoom // it does not: from its start
  return { x: place(left, right, width), y: place(top, bottom, height), zoom }
}
