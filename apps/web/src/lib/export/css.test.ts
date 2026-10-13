import { afterEach, describe, expect, it } from "vitest"
import {
  embeddedFace,
  embeddedFonts,
  faceKey,
  fontSource,
  pageStyles,
  unicodeRangeKey,
  type DeclaredFace,
} from "./css"

describe("unicodeRangeKey", () => {
  it("reads the same range the same way, however it is spelled", () => {
    expect(unicodeRangeKey("U+0000-00FF, U+0131, U+0152-0153")).toBe("0-ff,131-131,152-153")
    expect(unicodeRangeKey("u+0-ff,U+131 , U+152-153")).toBe("0-ff,131-131,152-153")
    expect(unicodeRangeKey("U+152-153, U+0-FF, U+131")).toBe("0-ff,131-131,152-153") // any order
  })

  it("takes a font that declares no range as covering every character", () => {
    expect(unicodeRangeKey("")).toBe("0-10ffff")
    expect(unicodeRangeKey("U+0-10FFFF")).toBe("0-10ffff")
  })

  it("understands a range written with wildcards", () => {
    expect(unicodeRangeKey("U+4??")).toBe("400-4ff")
  })
})

describe("faceKey", () => {
  it("is the same for a font as its rule declares it and as the browser reports it loaded", () => {
    const declared = {
      family: '"Geist Variable"',
      style: "normal",
      weight: "100 900",
      unicodeRange: "U+0000-00FF, U+0131",
    }
    const loaded = {
      family: "Geist Variable",
      style: "normal",
      weight: "100 900",
      unicodeRange: "U+0-FF, U+131",
    }
    expect(faceKey(declared)).toBe(faceKey(loaded))
    // A rule that leaves the defaults unsaid is the browser's normal, 400, every character.
    expect(faceKey({ family: "KaTeX_Main", style: "", weight: "", unicodeRange: "" })).toBe(
      faceKey({ family: "KaTeX_Main", style: "normal", weight: "400", unicodeRange: "U+0-10FFFF" }),
    )
    expect(faceKey({ family: "KaTeX_Main", style: "normal", weight: "bold", unicodeRange: "" })).toBe(
      faceKey({ family: "KaTeX_Main", style: "normal", weight: "700", unicodeRange: "" }),
    )
  })

  it("tells apart the weights, the styles and the alphabets of one family", () => {
    const face = { family: "KaTeX_Main", style: "normal", weight: "400", unicodeRange: "" }
    const keys = new Set([
      faceKey(face),
      faceKey({ ...face, weight: "700" }),
      faceKey({ ...face, style: "italic" }),
      faceKey({ ...face, unicodeRange: "U+400-45F" }),
      faceKey({ ...face, family: "KaTeX_Math" }),
    ])
    expect(keys.size).toBe(5)
  })
})

describe("fontSource", () => {
  it("prefers the compact format among the files a font is offered in", () => {
    expect(
      fontSource(
        'url(fonts/KaTeX_Main-Regular.woff) format("woff"), url("fonts/KaTeX_Main-Regular.woff2") format("woff2"), url(fonts/KaTeX_Main-Regular.ttf) format("truetype")',
      ),
    ).toEqual({ url: "fonts/KaTeX_Main-Regular.woff2", format: "woff2" })
    expect(fontSource('url("/files/geist-latin-wght-normal.woff2") format("woff2-variations")')).toEqual({
      url: "/files/geist-latin-wght-normal.woff2",
      format: "woff2-variations",
    })
  })

  it("takes the first file when none is compact, and none when there is no file to fetch", () => {
    expect(fontSource("url('a.ttf') format('truetype'), url(b.otf)")).toEqual({
      url: "a.ttf",
      format: "truetype",
    })
    expect(fontSource("url(a.ttf)")).toEqual({ url: "a.ttf", format: "" })
    expect(fontSource('local("Arial")')).toBeNull()
    expect(fontSource("url(data:font/woff2;base64,AAAA)")).toBeNull() // already in the rule
  })
})

const FACE: DeclaredFace = {
  family: "KaTeX_Math",
  style: "italic",
  weight: "400",
  unicodeRange: "",
  display: "block",
  stretch: "",
  url: "http://app.test/assets/KaTeX_Math-Italic.woff2",
  format: "woff2",
}

describe("embeddedFace", () => {
  it("declares a font whose file is in the declaration", () => {
    expect(embeddedFace(FACE, "data:font/woff2;base64,AAAA")).toBe(
      '@font-face { font-family: "KaTeX_Math"; font-style: italic; font-weight: 400; ' +
        'font-display: block; src: url(data:font/woff2;base64,AAAA) format("woff2"); }',
    )
  })

  it("keeps the characters a font is for, and its width if it has one", () => {
    const rule = embeddedFace(
      { ...FACE, family: "Geist Variable", style: "", weight: "100 900", unicodeRange: "U+0-FF", stretch: "75% 125%", display: "" },
      "data:font/woff2;base64,BBBB",
    )
    expect(rule).toContain("font-style: normal; font-weight: 100 900; font-stretch: 75% 125%; font-display: swap;")
    expect(rule).toContain("unicode-range: U+0-FF; }")
  })
})

describe("embeddedFonts", () => {
  const other: DeclaredFace = { ...FACE, family: "KaTeX_Fraktur", style: "normal", url: "http://app.test/f.woff2" }

  it("carries the fonts the browser loaded, and only those", async () => {
    const asked: string[] = []
    const css = await embeddedFonts([FACE, other], new Set([faceKey(FACE)]), async (url) => {
      asked.push(url)
      return "data:font/woff2;base64,AAAA"
    })

    expect(asked).toEqual([FACE.url]) // the other file is not even fetched
    expect(css).toContain('font-family: "KaTeX_Math"')
    expect(css).not.toContain("KaTeX_Fraktur")
  })

  it("leaves out a font whose file cannot be read", async () => {
    const css = await embeddedFonts([FACE, other], new Set([faceKey(FACE), faceKey(other)]), async (url) =>
      url === FACE.url ? null : "data:font/woff2;base64,CCCC",
    )

    expect(css).not.toContain("KaTeX_Math")
    expect(css).toContain('font-family: "KaTeX_Fraktur"')
  })
})

describe("pageStyles", () => {
  afterEach(() => document.head.querySelectorAll("style[data-test]").forEach((style) => style.remove()))

  it("reads the rules of the page and sets the declarations of fonts apart", () => {
    const style = document.createElement("style")
    style.dataset.test = "true"
    style.textContent = `
      .paper { max-width: 46rem; }
      @font-face { font-family: "KaTeX_Main"; font-style: normal; font-weight: 400; src: url(/assets/KaTeX_Main-Regular.woff2) format("woff2"), url(/assets/KaTeX_Main-Regular.woff) format("woff"); }
      @media print { .export-screen-only { display: none; } }
    `
    document.head.append(style)

    const { css, faces } = pageStyles()

    expect(css).toContain(".paper")
    expect(css).toContain("46rem")
    expect(css).toContain("@media print")
    expect(css).not.toContain("@font-face") // a font is carried with its file, or not at all
    expect(faces).toEqual([
      {
        family: "KaTeX_Main",
        style: "normal",
        weight: "400",
        unicodeRange: "",
        display: "",
        stretch: "",
        url: new URL("/assets/KaTeX_Main-Regular.woff2", document.baseURI).href,
        format: "woff2",
      },
    ])
  })
})
