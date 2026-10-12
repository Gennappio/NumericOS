import type { Paragraph, Root } from "mdast"
import { visit } from "unist-util-visit"
import type { VFile } from "vfile"

/**
 * A paragraph that is nothing but `$$ ... $$` on one line is displayed mathematics, as people
 * and models write it. remark-math only treats `$$` fences on lines of their own as displayed,
 * and renders the one-line form inline. This step turns that paragraph into a math block. It
 * changes the tree, never the source: positions stay those of the source text.
 */
export function remarkDisplayDollars() {
  return (tree: Root, file: VFile) => {
    const source = String(file)
    visit(tree, "paragraph", (node: Paragraph) => {
      if (node.children.length !== 1) return
      const child = node.children[0]
      if (child.type !== "inlineMath" || !child.position) return
      const start = child.position.start.offset
      const end = child.position.end.offset
      if (start === undefined || end === undefined) return
      if (source.slice(start, start + 2) !== "$$" || source.slice(end - 2, end) !== "$$") return
      // The shape mdast-util-math gives a math block, so that rehype-katex displays it.
      const block = node as unknown as Record<string, unknown>
      block.type = "math"
      block.value = child.value
      block.data = {
        hName: "pre",
        hChildren: [
          {
            type: "element",
            tagName: "code",
            properties: { className: ["language-math", "math-display"] },
            children: [{ type: "text", value: child.value }],
          },
        ],
      }
      delete block.children
    })
  }
}
