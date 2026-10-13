/**
 * The styles a shared document needs, taken from the page that is showing it.
 *
 * A document is shared as one file that must look as it does in the application, anywhere and
 * without the application. Its look is not written twice: the rules are read from the style
 * sheets of the running page, and the fonts the page actually loaded are put into the file.
 * A font file is asked for only if the browser used it, so a text without formulas carries
 * no formula font.
 */

export interface PageStyles {
  /** Every rule of the page, except the declarations of fonts. */
  css: string
  /** The fonts the page declares, each with where its file is. */
  faces: DeclaredFace[]
}

export interface DeclaredFace {
  family: string
  style: string
  weight: string
  /** As declared; empty when the font covers every character. */
  unicodeRange: string
  /** Other descriptors, kept as they are (`font-display`, `font-stretch`, ...). */
  display: string
  stretch: string
  /** The address of the font file, absolute. */
  url: string
  format: string
}

/** A font the browser has loaded: the descriptors a `FontFace` exposes. */
export interface LoadedFace {
  family: string
  style: string
  weight: string
  unicodeRange: string
}

const unquoted = (value: string) => value.trim().replace(/^["']|["']$/g, "")
const WEIGHTS: Record<string, string> = { normal: "400", bold: "700" }
const weightOf = (value: string) =>
  (value.trim() || "400")
    .split(/\s+/)
    .map((part) => WEIGHTS[part] ?? part)
    .join(" ")

/**
 * A unicode range in one spelling, whatever the browser's: `U+0000-00FF, u+131` and
 * `U+0-FF,U+131` are the same range. Nothing declared means every character.
 */
export function unicodeRangeKey(value: string): string {
  const ranges = value
    .split(",")
    .map((part) => part.trim().replace(/^u\+/i, ""))
    .filter(Boolean)
    .map((part) => {
      // "4??" is every code point from 400 to 4FF.
      const [from, to = from] = part.includes("?")
        ? [part.replace(/\?/g, "0"), part.replace(/\?/g, "F")]
        : part.split("-")
      return [parseInt(from, 16), parseInt(to, 16)] as const
    })
    .filter(([from, to]) => Number.isFinite(from) && Number.isFinite(to))
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
  if (ranges.length === 0) return "0-10ffff"
  return ranges.map(([from, to]) => `${from.toString(16)}-${to.toString(16)}`).join(",")
}

/** What tells one font file from another: the family, the style, the weights, the characters. */
export function faceKey(face: LoadedFace): string {
  return [
    unquoted(face.family).toLowerCase(),
    face.style.trim() || "normal",
    weightOf(face.weight),
    unicodeRangeKey(face.unicodeRange),
  ].join("|")
}

/** The first font file a `src` descriptor names, preferring the compact format. */
export function fontSource(src: string): { url: string; format: string } | null {
  const sources = [...src.matchAll(/url\(\s*(["']?)(.*?)\1\s*\)(?:\s*format\(\s*(["']?)(.*?)\3\s*\))?/g)]
    .map((match) => ({ url: match[2], format: match[4] ?? "" }))
    .filter((source) => source.url && !source.url.startsWith("data:"))
  return sources.find((source) => /\.woff2(\?|#|$)/.test(source.url)) ?? sources[0] ?? null
}

/** The rules of the page as text, and the fonts it declares. */
export function pageStyles(doc: Document = document): PageStyles {
  const rules: string[] = []
  const faces: DeclaredFace[] = []
  for (const sheet of doc.styleSheets) {
    let list: CSSRuleList
    try {
      list = sheet.cssRules
    } catch {
      // A style sheet of another origin cannot be read: the application has none of its own.
      continue
    }
    for (const item of list) {
      // Told by what it says, not by its class: not every environment names that class.
      if (!item.cssText.trimStart().startsWith("@font-face")) {
        rules.push(item.cssText)
        continue
      }
      const rule = item as CSSFontFaceRule
      const source = fontSource(rule.style.getPropertyValue("src"))
      if (!source) continue
      faces.push({
        family: unquoted(rule.style.getPropertyValue("font-family")),
        style: rule.style.getPropertyValue("font-style"),
        weight: rule.style.getPropertyValue("font-weight"),
        unicodeRange: rule.style.getPropertyValue("unicode-range"),
        display: rule.style.getPropertyValue("font-display"),
        stretch: rule.style.getPropertyValue("font-stretch"),
        url: new URL(source.url, sheet.href ?? doc.baseURI).href,
        format: source.format,
      })
    }
  }
  return { css: rules.join("\n"), faces }
}

/** The fonts the browser has loaded for the page, by what tells them apart. */
export function loadedFaces(doc: Document = document): Set<string> {
  const loaded = new Set<string>()
  // Absent where pages have no fonts of their own (a test environment): nothing is embedded.
  doc.fonts?.forEach((face) => {
    if (face.status === "loaded") loaded.add(faceKey(face))
  })
  return loaded
}

/** A declaration of a font whose file is in the declaration itself. */
export function embeddedFace(face: DeclaredFace, dataUrl: string): string {
  const lines = [
    `font-family: "${face.family}"`,
    `font-style: ${face.style.trim() || "normal"}`,
    `font-weight: ${face.weight.trim() || "400"}`,
    face.stretch.trim() && `font-stretch: ${face.stretch.trim()}`,
    `font-display: ${face.display.trim() || "swap"}`,
    `src: url(${dataUrl})${face.format ? ` format("${face.format}")` : ""}`,
    face.unicodeRange.trim() && `unicode-range: ${face.unicodeRange.trim()}`,
  ].filter(Boolean)
  return `@font-face { ${lines.join("; ")}; }`
}

/**
 * The declarations of the fonts in use, each carrying its file. `read` fetches a file as a
 * `data:` address; a font that cannot be read is left out, and the text falls back to the
 * reader's own fonts.
 */
export async function embeddedFonts(
  faces: DeclaredFace[],
  loaded: Set<string>,
  read: (url: string) => Promise<string | null>,
): Promise<string> {
  const used = faces.filter((face) => loaded.has(faceKey(face)))
  const embedded = await Promise.all(
    used.map(async (face) => {
      const data = await read(face.url)
      return data ? embeddedFace(face, data) : null
    }),
  )
  return embedded.filter((rule) => rule !== null).join("\n")
}
