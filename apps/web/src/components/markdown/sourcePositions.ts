import type { Element, ElementContent, Root, RootContent, Text } from "hast"

/**
 * Marks of where each piece of the rendered page comes from in the Markdown source, so that
 * a selection on the page can be turned into a range of the source and back.
 *
 * A *leaf* is the smallest piece a selection can be cut at:
 * - `data-leaf="t"`: a run of text whose characters map one to one to the source between
 *   `data-s` and `data-e` (offsets in UTF-16 units, as JavaScript indexes strings);
 * - `data-leaf="a"`: an atom, taken whole or not at all: a formula, code, an image, or text
 *   the source writes differently from what is shown (an escape, an entity, a line of a
 *   quote). A selection that touches an atom covers its whole source.
 */

const ATOMIC = new Set(["code", "pre", "img"])
/** Block atoms are wrapped in a div, the others in a span, to keep the markup valid. */
const BLOCK_ATOMS = new Set(["pre"])

type Range = { start: number; end: number }

function rangeOf(node: Element | Text): Range | null {
  const start = node.position?.start.offset
  const end = node.position?.end.offset
  return typeof start === "number" && typeof end === "number" && end > start
    ? { start, end }
    : null
}

function leaf(tagName: "span" | "div", kind: "t" | "a", range: Range, child: ElementContent): Element {
  return {
    type: "element",
    tagName,
    properties: { dataLeaf: kind, dataS: range.start, dataE: range.end },
    children: [child],
  }
}

function mark(children: ElementContent[], offset: number): ElementContent[] {
  const shifted = (range: Range): Range => ({ start: range.start + offset, end: range.end + offset })
  return children.map((child) => {
    if (child.type === "text") {
      const range = rangeOf(child)
      if (!range || child.value.trim() === "") return child
      const exact = child.value.length === range.end - range.start
      return leaf("span", exact ? "t" : "a", shifted(range), child)
    }
    if (child.type !== "element") return child
    if (ATOMIC.has(child.tagName)) {
      const range = rangeOf(child)
      const tagName = BLOCK_ATOMS.has(child.tagName) ? "div" : "span"
      return range ? leaf(tagName, "a", shifted(range), child) : child
    }
    child.children = mark(child.children, offset)
    return child
  })
}

/**
 * Wrap every leaf of the tree with where it comes from in the source. When the source is a
 * part of a longer text (one box of a pipeline), `offset` is where the part starts in it: the
 * marks then count from the start of the whole text, and the parts of one text can share a
 * page.
 */
export function rehypeSourcePositions({ offset = 0 }: { offset?: number } = {}) {
  return (tree: Root) => {
    tree.children = mark(tree.children as ElementContent[], offset) as RootContent[]
  }
}

export interface Slot {
  /** What is shown there; several slots after the same block share one place, in order. */
  id: string
  /** A source offset (UTF-16): the slot goes after the top-level block that contains it. */
  after: number
}

/**
 * Put an empty `div[data-slot]` after the top-level block that contains each given source
 * offset. The page renders something of its own there (a clarification next to its passage);
 * the text of the document is not changed.
 */
export function rehypeSlots({ slots }: { slots: Slot[] }) {
  return (tree: Root) => {
    if (slots.length === 0) return
    const blocks = tree.children
      .map((child, index) => ({ child, index }))
      .filter(({ child }) => child.type === "element" && rangeOf(child as Element) !== null)
    if (blocks.length === 0) return
    // For each block, the ids of the slots that go after it.
    const placed = new Map<number, string[]>()
    for (const slot of slots) {
      let target = blocks[0]
      for (const block of blocks) {
        if (rangeOf(block.child as Element)!.start < slot.after) target = block
      }
      placed.set(target.index, [...(placed.get(target.index) ?? []), slot.id])
    }
    const children: RootContent[] = []
    tree.children.forEach((child, index) => {
      children.push(child)
      const ids = placed.get(index)
      if (ids) {
        children.push({
          type: "element",
          tagName: "div",
          properties: { dataSlot: ids.join(" ") },
          children: [],
        })
      }
    })
    tree.children = children
  }
}
