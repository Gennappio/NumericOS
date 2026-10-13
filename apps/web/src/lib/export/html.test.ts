import { afterEach, describe, expect, it, vi } from "vitest"
import { fileName, inlineImages, readAsDataUrl, standalonePage } from "./html"

afterEach(() => vi.unstubAllGlobals())

describe("standalonePage", () => {
  it("is a whole page with its styles and fonts in it, and no script", () => {
    const page = standalonePage({
      title: "Pipeline of <Heat & Co>",
      css: ".paper { color: black; }",
      fonts: '@font-face { font-family: "KaTeX_Main"; src: url(data:font/woff2;base64,AAAA); }',
      body: '<article aria-label="A">text</article>',
    })

    expect(page.startsWith("<!doctype html>\n<html lang=\"en\">")).toBe(true)
    expect(page).toContain('<meta charset="utf-8">')
    expect(page).toContain("<title>Pipeline of &lt;Heat &amp; Co&gt;</title>") // text, not markup
    expect(page).toContain("<style>.paper { color: black; }</style>")
    expect(page).toContain("url(data:font/woff2;base64,AAAA)")
    expect(page).toContain('<body>\n<article aria-label="A">text</article>\n</body>')
    expect(page).not.toContain("<script")
    expect(page.endsWith("</html>\n")).toBe(true)
  })

  it("does not let a rule end the style element early", () => {
    const page = standalonePage({ title: "T", css: 'a::after { content: "</style>"; }', fonts: "", body: "" })

    expect(page.match(/<\/style>/g)).toHaveLength(2) // the two elements of the page, no third
  })
})

describe("fileName", () => {
  it("names the file after the project and what it holds", () => {
    expect(fileName("Heat 2D", "pipeline")).toBe("heat-2d-pipeline.html")
    expect(fileName("  Équation de la chaleur — v2 ", "theory")).toBe("equation-de-la-chaleur-v2-theory.html")
    expect(fileName("SEARCH", "Theory")).toBe("search-theory.html")
  })

  it("still has a name when nothing in the project's name can be kept", () => {
    expect(fileName("研究", "pipeline")).toBe("pipeline.html")
    expect(fileName("///", "")).toBe("document.html")
  })
})

describe("inlineImages", () => {
  function rendered(markup: string): HTMLElement {
    const root = document.createElement("div")
    root.innerHTML = markup
    return root
  }

  it("puts every image into the page and lets go of what only matters while loading", async () => {
    const root = rendered(
      '<img src="http://api.test/v1/projects/p/files/content?path=docs%2Fgrid.png" alt="The grid" loading="lazy">' +
        '<img src="data:image/png;base64,ALREADY" alt="inline">',
    )
    const asked: string[] = []

    const left = await inlineImages(root, async (url) => {
      asked.push(url)
      return "data:image/png;base64,GRID"
    })

    expect(asked).toEqual(["http://api.test/v1/projects/p/files/content?path=docs%2Fgrid.png"])
    expect(left).toBe(0)
    const [grid, inline] = root.querySelectorAll("img")
    expect(grid.getAttribute("src")).toBe("data:image/png;base64,GRID")
    expect(grid.hasAttribute("loading")).toBe(false)
    expect(grid.alt).toBe("The grid")
    expect(inline.getAttribute("src")).toBe("data:image/png;base64,ALREADY") // untouched
  })

  it("leaves an image that cannot be read where it was, and counts it", async () => {
    const root = rendered('<img src="https://elsewhere.test/a.png" alt="A"><img src="http://api.test/b.png" alt="B">')

    const left = await inlineImages(root, async (url) => (url.includes("elsewhere") ? null : "data:image/png;base64,B"))

    expect(left).toBe(1)
    const [a, b] = root.querySelectorAll("img")
    expect(a.getAttribute("src")).toBe("https://elsewhere.test/a.png")
    expect(b.getAttribute("src")).toBe("data:image/png;base64,B")
  })

  it("has nothing to do for a text without images", async () => {
    expect(await inlineImages(rendered("<p>no figure</p>"), async () => null)).toBe(0)
  })
})

describe("readAsDataUrl", () => {
  it("reads a file as an address that holds it, named by its kind", async () => {
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0xff, 0x00])
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(bytes, { headers: { "Content-Type": "image/png; charset=binary" } })),
    )

    expect(await readAsDataUrl("http://api.test/grid.png")).toBe("data:image/png;base64,iVBOR/8A")
  })

  it("reads a file larger than one piece whole", async () => {
    const bytes = new Uint8Array(100_000).map((_, index) => index % 251)
    vi.stubGlobal("fetch", vi.fn(async () => new Response(bytes, { headers: { "Content-Type": "font/woff2" } })))

    const address = await readAsDataUrl("http://app.test/font.woff2")

    expect(address?.startsWith("data:font/woff2;base64,")).toBe(true)
    const back = Uint8Array.from(atob(address!.split(",")[1]), (character) => character.charCodeAt(0))
    expect(back).toEqual(bytes)
  })

  it("is null for a file that is not there or cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 404 })))
    expect(await readAsDataUrl("http://api.test/gone.png")).toBeNull()

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))
    expect(await readAsDataUrl("https://elsewhere.test/a.png")).toBeNull()
  })
})
