import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Markdown } from "@/components/markdown/Markdown"
import { fromCodePoints, rangeToSource, sourceToRanges, toCodePoints } from "./sourceMap"

const SOURCE = [
  "# Heat *2D*",
  "",
  "The scheme is **stable** when $r \\le 1/2$, see `step()` and the bound below.",
  "",
  "$$u_t = \\alpha \\nabla^2 u \\tag{1}$$",
  "",
  "- first item with AT&amp;T",
  "- second item",
  "",
  "```python",
  "u = step(u)",
  "```",
  "",
  "Last paragraph.",
].join("\n")

function page() {
  const { container } = render(<Markdown source={SOURCE} positions />)
  return container.querySelector<HTMLElement>(".markdown")!
}

/** A range from `from` in the text node that contains it to the end of `to` in its own. */
function select(root: HTMLElement, from: string, to: string = from): Range {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const range = document.createRange()
  let started = false
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    if (!started && node.data.includes(from)) {
      range.setStart(node, node.data.indexOf(from))
      started = true
    }
    if (started && node.data.includes(to)) {
      range.setEnd(node, node.data.indexOf(to) + to.length)
      return range
    }
  }
  throw new Error(`could not select ${from} … ${to}`)
}

function selected(root: HTMLElement, from: string, to?: string): string {
  const found = rangeToSource(root, select(root, from, to))
  return found ? SOURCE.slice(found.start, found.end) : "(nothing)"
}

describe("selection to source", () => {
  it("is exact to the character inside plain text", () => {
    const root = page()

    expect(selected(root, "scheme is")).toBe("scheme is")
    expect(selected(root, "Last para")).toBe("Last para")
    expect(selected(root, "econd ite")).toBe("econd ite")
  })

  it("spans formatting by taking the source between its ends", () => {
    const root = page()

    expect(selected(root, "scheme is", "stable")).toBe("scheme is **stable")
    expect(selected(root, "Heat", "2D")).toBe("Heat *2D")
    expect(selected(root, "stable", "when")).toBe("stable** when")
  })

  it("takes a formula, code or an escaped text whole when it is touched", () => {
    const root = page()
    const formula = root.querySelector(".katex")!
    const inside = document.createRange()
    inside.selectNodeContents(formula.querySelector(".katex-html")!)

    const found = rangeToSource(root, inside)!
    expect(SOURCE.slice(found.start, found.end)).toBe("$r \\le 1/2$")
    expect(selected(root, "step")).toBe("`step()`")
    expect(selected(root, "u = step")).toBe("```python\nu = step(u)\n```")
    // The source writes the ampersand as an entity: the run of text is taken whole.
    expect(selected(root, "AT&T")).toBe("first item with AT&amp;T")
    // From plain text into a formula: exact at one end, the whole formula at the other.
    const display = root.querySelector(".katex-display")!
    const across = select(root, "bound below")
    across.setEnd(display.querySelector(".katex-html")!, 1)
    const wide = rangeToSource(root, across)!
    expect(SOURCE.slice(wide.start, wide.end)).toBe(
      "bound below.\n\n$$u_t = \\alpha \\nabla^2 u \\tag{1}$$",
    )
  })

  it("is nothing for a selection that holds no text", () => {
    const root = page()
    const empty = document.createRange()
    empty.setStart(root, 0)
    empty.setEnd(root, 0)

    expect(rangeToSource(root, empty)).toBeNull()
  })
})

describe("source to page", () => {
  it("finds the pieces of the page that show a range of the source", () => {
    const root = page()
    const start = SOURCE.indexOf("scheme is")
    const end = SOURCE.indexOf("when") + "when".length

    const ranges = sourceToRanges(root, { start, end })

    expect(ranges.map((range) => range.toString())).toEqual(["scheme is ", "stable", " when"])
  })

  it("shows a formula whole for any range that reaches into it", () => {
    const root = page()
    const start = SOURCE.indexOf("\\le")

    const [range] = sourceToRanges(root, { start, end: start + 3 })

    expect(range.commonAncestorContainer).toBe(root.querySelector("[data-leaf=a]"))
  })

  it("goes there and back to the same range", () => {
    const root = page()
    const start = SOURCE.indexOf("econd")
    const source = { start, end: start + 9 }

    const [range] = sourceToRanges(root, source)

    expect(rangeToSource(root, range)).toEqual(source)
  })
})

describe("code points", () => {
  it("counts an astral character once, as the API does", () => {
    const text = "Errore 😀 di Δt²"

    expect(toCodePoints(text, text.indexOf("Δ"))).toBe(text.indexOf("Δ") - 1)
    expect(fromCodePoints(text, toCodePoints(text, text.indexOf("Δ")))).toBe(text.indexOf("Δ"))
    expect(fromCodePoints(text, 0)).toBe(0)
    expect(toCodePoints(text, text.length)).toBe([...text].length)
  })
})
