/**
 * Highlights drawn with the CSS Custom Highlight API: ranges of the page are registered under
 * a name and styled with `::highlight(name)`. The page itself is not changed, so what React
 * renders stays what React rendered. Several parts of a page share the names: each registers
 * its ranges under its own owner key, and the registry holds the union.
 */

const owners = new Map<string, Map<string, Range[]>>()

/**
 * The colours follow the kinds of comment. The rules are added to the page when the first
 * highlight is drawn, not kept in the stylesheet: the build's CSS minifier does not know the
 * `::highlight()` pseudo-element yet and warns about every rule.
 */
const STYLES = `
::highlight(nos-clarification) { background-color: rgb(56 189 248 / 0.45); }
::highlight(nos-change) { background-color: rgb(251 146 60 / 0.5); }
::highlight(nos-note) { background-color: rgb(167 139 250 / 0.45); }
::highlight(nos-settled) { background-color: rgb(110 231 183 / 0.45); }
::highlight(nos-draft) { background-color: rgb(129 140 248 / 0.45); }
::highlight(nos-focus) { background-color: rgb(250 204 21 / 0.8); }
`
const STYLE_ID = "nos-highlight-styles"

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return
  const style = document.createElement("style")
  style.id = STYLE_ID
  style.textContent = STYLES
  document.head.append(style)
}

export function highlightsSupported(): boolean {
  return typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined"
}

function publish(names: Iterable<string>): void {
  if (!highlightsSupported()) return
  ensureStyles()
  for (const name of names) {
    const ranges = [...owners.values()].flatMap((groups) => groups.get(name) ?? [])
    if (ranges.length === 0) CSS.highlights.delete(name)
    else CSS.highlights.set(name, new Highlight(...ranges))
  }
}

/** Replace the highlights of one owner; `groups` maps a highlight name to its ranges. */
export function setHighlights(owner: string, groups: Record<string, Range[]>): void {
  const before = owners.get(owner)
  owners.set(owner, new Map(Object.entries(groups)))
  publish(new Set([...(before?.keys() ?? []), ...Object.keys(groups)]))
}

export function clearHighlights(owner: string): void {
  const before = owners.get(owner)
  if (!before) return
  owners.delete(owner)
  publish(before.keys())
}
