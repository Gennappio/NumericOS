import { describe, expect, it } from "vitest"
import { layoutPipeline, startViewport } from "./layout"

const box = (id: string, height = 200) => ({ id, width: 320, height })

describe("layoutPipeline", () => {
  it("puts the boxes from left to right along the arrows, without overlap", () => {
    const places = layoutPipeline(
      [box("read"), box("grid", 260), box("step"), box("write", 120)],
      [
        { source: "read", target: "grid" },
        { source: "grid", target: "step" },
        { source: "step", target: "write" },
      ],
    )

    expect(places.read.x).toBeLessThan(places.grid.x)
    expect(places.grid.x - places.read.x).toBeGreaterThan(320) // room for the arrow's words
    expect(places.grid.x).toBeLessThan(places.step.x)
    expect(places.step.x).toBeLessThan(places.write.x)
    // Boxes of different heights in a row share their middle: the arrows run straight.
    expect(places.read.y + 100).toBeCloseTo(places.grid.y + 130)
    expect(places.read.y + 100).toBeCloseTo(places.write.y + 60)
  })

  it("stacks the branches of a fork one above the other", () => {
    const places = layoutPipeline(
      [box("read"), box("mesh"), box("solve"), box("plot"), box("save")],
      [
        { source: "read", target: "solve" },
        { source: "mesh", target: "solve" },
        { source: "solve", target: "plot" },
        { source: "solve", target: "save" },
      ],
    )

    expect(places.read.x).toBe(places.mesh.x)
    expect(Math.abs(places.read.y - places.mesh.y)).toBeGreaterThanOrEqual(200)
    expect(places.plot.x).toBe(places.save.x)
    expect(places.solve.x).toBeGreaterThan(places.read.x)
    expect(places.plot.x).toBeGreaterThan(places.solve.x)
  })

  it("keeps the order of a run when an arrow closes a loop", () => {
    const places = layoutPipeline(
      [box("init"), box("step"), box("check"), box("write")],
      [
        { source: "init", target: "step" },
        { source: "step", target: "check" },
        { source: "check", target: "step" }, // not converged: once more
        { source: "check", target: "write" },
      ],
    )

    expect(places.init.x).toBeLessThan(places.step.x)
    expect(places.step.x).toBeLessThan(places.check.x)
    expect(places.check.x).toBeLessThan(places.write.x)
  })

  it("lines the boxes up in the order they were written when no arrow says more", () => {
    const places = layoutPipeline([box("a"), box("b"), box("c")], [])

    expect(places.a.x).toBeLessThan(places.b.x)
    expect(places.b.x).toBeLessThan(places.c.x)
    expect(places.a.y).toBe(places.b.y)
  })

  it("ignores an arrow to a box that is not on the board", () => {
    const places = layoutPipeline([box("a"), box("b")], [{ source: "a", target: "gone" }])

    expect(Object.keys(places)).toEqual(["a", "b"])
    expect(places.a.x).toBeLessThan(places.b.x) // as if there were no arrow at all
  })
})

describe("startViewport", () => {
  const placed = (id: string, x: number, y = 0, height = 200) => ({ ...box(id, height), x, y })

  it("shows a small board whole, at full size, in the middle", () => {
    const view = startViewport([placed("a", 0), placed("b", 470)], 1200, 600)

    expect(view.zoom).toBe(1)
    expect(view.x).toBe((1200 - 790) / 2)
    expect(view.y).toBe((600 - 200) / 2)
  })

  it("shrinks a board a little to show it whole while its text stays readable", () => {
    const view = startViewport([placed("a", 0), placed("b", 470), placed("c", 940)], 1200, 600)

    expect(view.zoom).toBeCloseTo((1200 - 64) / 1260)
    expect(view.zoom).toBeGreaterThanOrEqual(0.85)
    expect(view.x).toBeCloseTo(32) // it fills the width, margins apart
  })

  it("shows the beginning of a long board at full size rather than all of it too small", () => {
    const boxes = Array.from({ length: 9 }, (_, index) => placed(`b${index}`, 100 + index * 470, 40))
    const view = startViewport(boxes, 1000, 600)

    expect(view.zoom).toBe(1)
    expect(view.x).toBe(32 - 100) // the first box at the left margin
    expect(view.y).toBe((600 - 200) / 2 - 40) // one row: in the middle of the height
  })

  it("has nothing to compute for an empty board or before the page has a size", () => {
    expect(startViewport([], 1000, 600)).toEqual({ x: 0, y: 0, zoom: 1 })
    expect(startViewport([placed("a", 0)], 0, 0)).toEqual({ x: 0, y: 0, zoom: 1 })
  })
})
