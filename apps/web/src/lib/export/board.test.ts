import { describe, expect, it } from "vitest"
import { drawBoard } from "./board"

const SIZES = [
  { id: "read", width: 320, height: 160 },
  { id: "step", width: 320, height: 240 },
  { id: "write", width: 320, height: 120 },
]
const EDGES = [
  { source: "read", target: "step", label: "parameters" },
  { source: "step", target: "write", label: "" },
]
/** The two ends of a path: where its line starts and where it stops. */
function ends(path: string): [number[], number[]] {
  const numbers = path.match(/-?\d+(\.\d+)?/g)!.map(Number)
  return [numbers.slice(0, 2), numbers.slice(-2)]
}

describe("drawBoard", () => {
  it("measures the boxes from the corner of the drawing, with a margin around them", () => {
    const board = drawBoard(
      SIZES,
      { read: { x: -200, y: 40 }, step: { x: 270, y: 0 }, write: { x: 740, y: 60 } },
      EDGES,
      48,
    )

    expect(board.boxes.map((box) => [box.id, box.x, box.y])).toEqual([
      ["read", 48, 88],
      ["step", 518, 48],
      ["write", 988, 108],
    ])
    expect(board.width).toBe(988 + 320 + 48)
    expect(board.height).toBe(48 + 240 + 48)
  })

  it("draws every arrow from the right of a box to the left of the next, at mid height", () => {
    const board = drawBoard(
      SIZES,
      { read: { x: 0, y: 40 }, step: { x: 470, y: 0 }, write: { x: 940, y: 60 } },
      EDGES,
      0,
    )
    const [first, second] = board.arrows

    expect(first.key).toBe("read->step")
    expect(ends(first.path)).toEqual([
      [320, 40 + 80],
      [470, 120],
    ])
    expect(first.label).toBe("parameters")
    // The words of an arrow go between the two boxes.
    expect(first.labelX).toBeGreaterThan(320)
    expect(first.labelX).toBeLessThan(470)
    expect(ends(second.path)).toEqual([
      [790, 120],
      [940, 60 + 60],
    ])
    expect(board.arrows.map((arrow) => arrow.back)).toEqual([false, false])
  })

  it("marks an arrow that points back to an earlier box", () => {
    const board = drawBoard(
      SIZES,
      { read: { x: 0, y: 0 }, step: { x: 470, y: 0 }, write: { x: 940, y: 0 } },
      [...EDGES, { source: "write", target: "step", label: "next step" }],
    )

    expect(board.arrows.map((arrow) => [arrow.key, arrow.back])).toEqual([
      ["read->step", false],
      ["step->write", false],
      ["write->step", true],
    ])
  })

  it("draws no arrow to a box that is not there, and nothing for an empty board", () => {
    const board = drawBoard(SIZES, {}, [{ source: "read", target: "gone", label: "x" }])

    expect(board.arrows).toEqual([])
    expect(board.boxes).toHaveLength(3) // without a place they are at the corner
    expect(drawBoard([], {}, EDGES)).toEqual({ width: 0, height: 0, boxes: [], arrows: [] })
  })
})
