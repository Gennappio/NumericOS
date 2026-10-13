import { describe, expect, it } from "vitest"
import { pipelineRecord } from "@/test/agent"
import { partOf, sections } from "./pipeline"

const document = pipelineRecord()
const text = document.markdown
const parts = sections(text, document.pipeline!)

describe("sections", () => {
  it("finds the section of every box in the text, as JavaScript indexes it", () => {
    const loop = parts.boxes.get("time-loop")!

    // The emoji of the title is two units here and one code point for the API.
    expect(loop.start).toBe(document.pipeline!.nodes[1].start + 1)
    expect(text.slice(loop.start, loop.end)).toBe(
      "## Advance in time\n\n" +
        "The explicit scheme updates every point from its four neighbours.\n\n" +
        "- stable when $r \\le 1/4$\n- first order in time",
    )
    expect(text.slice(parts.boxes.get("results")!.start)).toBe(
      "## Write the results\n\nThe final field goes to the run directory.",
    )
    expect([...parts.boxes.keys()]).toEqual(["parameters", "time-loop", "results"])
  })

  it("takes what is before the first box as the header, without the gap that follows", () => {
    expect(text.slice(parts.header.start, parts.header.end)).toBe(
      "# Pipeline of the 2D heat solver 😀\n\n" +
        "One run reads its parameters, advances the scheme and writes the final field.",
    )
  })

  it("has only a header for a pipeline without boxes", () => {
    const empty = sections("# Nothing\n\nNo box.", { nodes: [], edges: [] })

    expect(empty.header).toEqual({ start: 0, end: 18 })
    expect(empty.boxes.size).toBe(0)
  })
})

describe("partOf", () => {
  const range = (passage: string) => {
    const start = text.indexOf(passage)
    return { start, end: start + passage.length }
  }

  it("says which part a passage lies in", () => {
    expect(partOf(parts, range("advances the scheme"))).toBe("header")
    expect(partOf(parts, range("Pipeline of the 2D"))).toBe("header")
    expect(partOf(parts, range("four neighbours"))).toBe("time-loop")
    expect(partOf(parts, range("Advance in time"))).toBe("time-loop") // its title is its text
    expect(partOf(parts, range("first order in time"))).toBe("time-loop") // up to its end
    expect(partOf(parts, range("The final field goes"))).toBe("results")
  })

  it("has no part for a passage that runs from one box into the next", () => {
    const start = text.indexOf("first order")
    const end = text.indexOf("Write the results") + 5

    expect(partOf(parts, { start, end })).toBeNull()
    expect(partOf(parts, { start: text.indexOf("final field."), end: text.indexOf("Read the") + 4 })).toBeNull()
  })
})
