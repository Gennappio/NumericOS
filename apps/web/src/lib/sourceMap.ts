/**
 * From a selection on a rendered page to a range of its Markdown source, and back.
 *
 * The page carries marks of where each piece comes from (see
 * `components/markdown/sourcePositions.ts`). Offsets here are UTF-16 units, as JavaScript
 * indexes strings; the API counts Unicode code points, and the two converters below are the
 * only place where one becomes the other.
 */

export interface SourceRange {
  start: number
  end: number
}

/** The number of code points before a UTF-16 index. */
export function toCodePoints(source: string, index: number): number {
  let count = 0
  for (let at = 0; at < index && at < source.length; count += 1) {
    at += source.codePointAt(at)! > 0xffff ? 2 : 1
  }
  return count
}

/** The UTF-16 index of a code point offset. */
export function fromCodePoints(source: string, offset: number): number {
  let at = 0
  for (let count = 0; count < offset && at < source.length; count += 1) {
    at += source.codePointAt(at)! > 0xffff ? 2 : 1
  }
  return at
}

interface Leaf {
  element: HTMLElement
  exact: boolean
  start: number
  end: number
}

function leavesOf(root: HTMLElement): Leaf[] {
  return [...root.querySelectorAll<HTMLElement>("[data-leaf]")].map((element) => ({
    element,
    exact: element.dataset.leaf === "t",
    start: Number(element.dataset.s),
    end: Number(element.dataset.e),
  }))
}

/**
 * The range of the source a selection covers, or null when it covers nothing of the text.
 * Inside plain text the range is exact to the character; a formula, code or an image that
 * the selection touches is covered whole.
 */
export function rangeToSource(root: HTMLElement, range: Range): SourceRange | null {
  let start = Infinity
  let end = -Infinity
  for (const leaf of leavesOf(root)) {
    if (!range.intersectsNode(leaf.element)) continue
    const text = leaf.element.firstChild
    if (leaf.exact && text instanceof Text) {
      const from = range.startContainer === text ? range.startOffset : 0
      const to = range.endContainer === text ? range.endOffset : text.length
      // A boundary placed between this text and its neighbour selects nothing of it.
      if (!range.intersectsNode(text) || from >= to) continue
      start = Math.min(start, leaf.start + from)
      end = Math.max(end, leaf.start + to)
    } else {
      // The selection may only touch the atom's edge: it must hold some of its content.
      const inside = document.createRange()
      inside.selectNodeContents(leaf.element)
      const touchesOnly =
        range.compareBoundaryPoints(Range.END_TO_START, inside) >= 0 ||
        range.compareBoundaryPoints(Range.START_TO_END, inside) <= 0
      if (touchesOnly) continue
      start = Math.min(start, leaf.start)
      end = Math.max(end, leaf.end)
    }
  }
  return end > start ? { start, end } : null
}

/** The pieces of the page that show a range of the source, to highlight them. */
export function sourceToRanges(root: HTMLElement, source: SourceRange): Range[] {
  const ranges: Range[] = []
  for (const leaf of leavesOf(root)) {
    if (leaf.end <= source.start || leaf.start >= source.end) continue
    const range = document.createRange()
    const text = leaf.element.firstChild
    if (leaf.exact && text instanceof Text) {
      range.setStart(text, Math.max(source.start, leaf.start) - leaf.start)
      range.setEnd(text, Math.min(source.end, leaf.end) - leaf.start)
    } else {
      range.selectNodeContents(leaf.element)
    }
    ranges.push(range)
  }
  return ranges
}

/** The source offset under a point of the page (a click), or null outside the text. */
export function offsetAtPoint(root: HTMLElement, x: number, y: number): number | null {
  let node: Node | null = null
  let offset = 0
  if (typeof document.caretPositionFromPoint === "function") {
    const caret = document.caretPositionFromPoint(x, y)
    if (caret) [node, offset] = [caret.offsetNode, caret.offset]
  } else if (typeof document.caretRangeFromPoint === "function") {
    const caret = document.caretRangeFromPoint(x, y)
    if (caret) [node, offset] = [caret.startContainer, caret.startOffset]
  }
  if (!node || !root.contains(node)) return null
  const element = node instanceof Element ? node : node.parentElement
  const leaf = element?.closest<HTMLElement>("[data-leaf]")
  if (!leaf || !root.contains(leaf)) return null
  const start = Number(leaf.dataset.s)
  return leaf.dataset.leaf === "t" && node instanceof Text ? start + offset : start
}
