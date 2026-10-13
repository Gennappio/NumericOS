import { afterEach, describe, expect, it, vi } from "vitest"
import { writePositions } from "@/components/pipeline/positions"
import { documentRecord, pipelineRecord } from "@/test/agent"
import { projectRecord } from "@/test/runs"
import { sharePipeline, shareTheory } from "./exportDocument"

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

/** A page parsed from the file, to look into it as a reader's browser would. */
function opened(html: string): Document {
  return new DOMParser().parseFromString(html, "text/html")
}

/** Every image of the project answers with the same small picture. */
function stubImages() {
  const asked: string[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input))
      return new Response(new Uint8Array([0x89, 0x50, 0x4e, 0x47]), {
        headers: { "Content-Type": "image/png" },
      })
    }),
  )
  return asked
}

describe("shareTheory", () => {
  it("makes one page of the theory, with its formulas rendered and its figure inside", async () => {
    const asked = stubImages()
    const project = projectRecord({ name: "Heat 2D" })

    const file = await shareTheory(project, documentRecord())
    const page = opened(file.html)

    expect(file.name).toBe("heat-2d-theory.html")
    expect(file.imagesLeftOutside).toBe(0)
    expect(page.title).toBe("Explicit scheme for the 2D heat equation")
    expect(page.querySelector(".paper h1")?.textContent).toBe("Explicit scheme for the 2D heat equation")
    expect(page.querySelector(".paper .katex-display")).not.toBeNull()
    // The figure was fetched from the project once and is in the page itself.
    expect(asked).toEqual(["http://127.0.0.1:8765/v1/projects/prj_1/files/content?path=docs%2Fgrid.png"])
    expect(page.querySelector("img")?.getAttribute("src")).toMatch(/^data:image\/png;base64,/)
    expect(page.querySelector("img")?.alt).toBe("The grid")
    // Whose it is, and where it comes from.
    expect(page.body.textContent).toContain("Heat 2D · Theory")
    expect(page.body.textContent).toMatch(/Version 1 · written by claude-fable-5-1 on .* from 2 files of the project/)
    expect(page.body.textContent).toContain("exported from NumericOS on")
    expect(page.querySelector("script")).toBeNull()
    expect(page.querySelector("[data-leaf]")).toBeNull() // a copy is read, not commented
    // What was rendered to make it is gone from the page it was made on.
    expect(document.body.querySelector("[aria-hidden=true]")).toBeNull()
  })

  it("tells the reader when the code changed after the text was written", async () => {
    stubImages()

    const file = await shareTheory(
      projectRecord(),
      documentRecord({ stale: true, changed_sources: ["heat2d.py", "docs/notes.md"] }),
    )

    expect(opened(file.html).body.textContent).toContain(
      "2 files this was written from have changed since: heat2d.py, docs/notes.md. What follows describes the project as it was.",
    )
  })

  it("says how many figures it could not take in", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))

    const file = await shareTheory(projectRecord(), documentRecord())

    expect(file.imagesLeftOutside).toBe(1)
    expect(opened(file.html).querySelector("img")?.getAttribute("src")).toContain("/files/content?path=")
  })
})

describe("sharePipeline", () => {
  it("makes one page of the board: a still box per part, the arrows drawn and in words", async () => {
    const document_ = pipelineRecord()
    const file = await sharePipeline(projectRecord({ name: "Heat 2D" }), document_, document_.pipeline!)
    const page = opened(file.html)

    expect(file.name).toBe("heat-2d-pipeline.html")
    expect(page.title).toBe("Pipeline of the 2D heat solver 😀")
    expect(page.querySelector(".pipeline-header h1")?.textContent).toBe("Pipeline of the 2D heat solver 😀")
    const boxes = [...page.querySelectorAll(".export-board article")]
    expect(boxes.map((box) => box.getAttribute("aria-label"))).toEqual([
      "Read the parameters",
      "Advance in time",
      "Write the results",
    ])
    // Still: nothing says a box can be dragged, and the text has no marks for comments.
    expect(page.querySelector(".pipeline-drag")).toBeNull()
    expect(page.querySelector("[title='Drag to move this box']")).toBeNull()
    expect(page.querySelector("[data-leaf]")).toBeNull()
    expect(boxes[1].textContent).toContain("from its four neighbours")
    expect(boxes[1].querySelector(".katex")).not.toBeNull()
    // Each box has its place, and each arrow its line and its words.
    expect(boxes.every((box) => (box.parentElement as HTMLElement).style.left !== "")).toBe(true)
    expect(page.querySelectorAll(".export-board svg path[marker-end]")).toHaveLength(2)
    expect([...page.querySelectorAll(".export-board .pipeline-arrow-label")].map((label) => label.textContent)).toEqual([
      "n, alpha, dt", // the arrow without words has none
    ])
    expect(
      [...page.querySelectorAll('[aria-label="Arrows of the pipeline"] li')].map((item) => item.textContent),
    ).toEqual(["Read the parametersAdvance in time· n, alpha, dt", "Advance in timeWrite the results"])
    // For paper: the parts one under the other, in the order of a run.
    const parts = [...page.querySelectorAll(".export-print-only .export-part")]
    expect(parts.map((part) => part.querySelector("h2")?.textContent)).toEqual([
      "Read the parameters",
      "Advance in time",
      "Write the results",
    ])
    expect(parts[1].textContent).toContain("Stage · repeats: every time step")
    expect(parts[1].textContent).toContain("heat2d.py, src/stencil.py")
    expect(page.body.textContent).toContain("Heat 2D · Pipeline")
    expect(page.querySelector("script")).toBeNull()
    expect(document.body.querySelector("[aria-hidden=true]")).toBeNull()
  })

  it("puts the boxes where the researcher left them on the board", async () => {
    const document_ = pipelineRecord()
    writePositions(document_.id, document_.version, {
      parameters: { x: 100, y: 500 },
      "time-loop": { x: 900, y: 100 },
      results: { x: 100, y: 100 },
    })

    const file = await sharePipeline(projectRecord(), document_, document_.pipeline!)
    const place = (title: string) => {
      const box = opened(file.html).querySelector(`.export-board article[aria-label="${title}"]`)!
      const style = (box.parentElement as HTMLElement).style
      return [parseInt(style.left, 10), parseInt(style.top, 10)]
    }

    // Measured from the corner of the drawing, with its margin: the arrangement is kept.
    expect(place("Write the results")).toEqual([48, 48])
    expect(place("Read the parameters")).toEqual([48, 448])
    expect(place("Advance in time")).toEqual([848, 48])
  })
})
