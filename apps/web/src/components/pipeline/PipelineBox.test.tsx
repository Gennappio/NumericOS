import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { sections } from "@/lib/pipeline"
import { pipelineRecord } from "@/test/agent"
import { PipelineBox } from "./PipelineBox"

const document = pipelineRecord()
const parts = sections(document.markdown, document.pipeline!)

function open(id: string, changed: string[] = []) {
  const node = document.pipeline!.nodes.find((item) => item.id === id)!
  const part = parts.boxes.get(id)!
  return render(
    <PipelineBox
      node={node}
      source={document.markdown.slice(part.start, part.end)}
      offset={part.start}
      slots={[]}
      renderSlot={() => null}
      changed={changed}
    />,
  )
}

describe("PipelineBox", () => {
  it("shows a part of the program: its kind, its title, its description, its files", () => {
    const { container } = open("time-loop")

    const box = screen.getByRole("article", { name: "Advance in time" })
    expect(box).toHaveAttribute("data-kind", "process")
    expect(within(box).getByText("Stage")).toBeVisible()
    expect(within(box).getByRole("heading", { level: 2, name: "Advance in time" })).toBeVisible()
    expect(within(box).getByText(/updates every point from its four neighbours/)).toBeVisible()
    expect(container.querySelector(".katex")).not.toBeNull() // formulas as in every text
    expect(within(box).getByText("every time step")).toBeVisible()
    // Files by their name; the whole path is a hover away.
    const files = within(box).getByRole("list", { name: "Files of Advance in time" })
    expect(within(files).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "heat2d.py",
      "stencil.py",
    ])
    expect(within(files).getByText("stencil.py")).toHaveAttribute("title", "src/stencil.py")
    expect(box).toHaveAttribute("data-changed", "false")
    expect(within(box).queryByRole("status")).toBeNull()
  })

  it("marks its text with where it is in the whole pipeline, so that it can be commented", () => {
    const { container } = open("time-loop")
    const text = document.markdown
    const leaf = [...container.querySelectorAll<HTMLElement>("[data-leaf=t]")].find(
      (element) => element.textContent === "Advance in time",
    )!

    // Counted from the start of the pipeline's text, not of the box.
    expect(Number(leaf.dataset.s)).toBe(text.indexOf("Advance in time"))
    expect(text.slice(Number(leaf.dataset.s), Number(leaf.dataset.e))).toBe("Advance in time")
    const formula = container.querySelector<HTMLElement>("[data-leaf=a]")!
    expect(text.slice(Number(formula.dataset.s), Number(formula.dataset.e))).toBe("$r \\le 1/4$")
  })

  it("says so when the code of the part changed since, and which file", () => {
    open("time-loop", ["heat2d.py"])

    const box = screen.getByRole("article", { name: "Advance in time" })
    expect(box).toHaveAttribute("data-changed", "true")
    expect(within(box).getByRole("status")).toHaveTextContent(
      "The code of this part changed since this was written.",
    )
    expect(within(box).getByText("heat2d.py")).toHaveAttribute("title", "heat2d.py (changed since)")
    expect(within(box).getByText("stencil.py")).toHaveAttribute("title", "src/stencil.py")
  })

  it("has no list of files and no loop mark when the part has neither", () => {
    open("results")

    const box = screen.getByRole("article", { name: "Write the results" })
    expect(box).toHaveAttribute("data-kind", "output")
    expect(within(box).getByText("Output")).toBeVisible()
    expect(within(box).queryByRole("list")).toBeNull()
    expect(within(box).queryByTitle("This part repeats")).toBeNull()
  })
})
