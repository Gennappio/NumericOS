import { useMemo, type ReactNode } from "react"
import ReactMarkdown, { type Options } from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import "katex/dist/katex.min.css"
import { remarkDisplayDollars } from "@/components/markdown/displayMath"
import {
  rehypeSlots,
  rehypeSourcePositions,
  type Slot,
} from "@/components/markdown/sourcePositions"
import { cn } from "@/lib/utils"

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkDisplayDollars]
// A formula KaTeX cannot parse is shown as its source in red, never thrown.
const KATEX: NonNullable<Options["rehypePlugins"]>[number] = [
  rehypeKatex,
  { throwOnError: false, strict: "ignore" },
]
// Code blocks that name their language are coloured; one that does not is left as it is.
const HIGHLIGHT: NonNullable<Options["rehypePlugins"]>[number] = [
  rehypeHighlight,
  { detect: false },
]
const REHYPE_PLUGINS = [KATEX, HIGHLIGHT]

interface MarkdownProps {
  source: string
  className?: string
  /**
   * Where an image whose address is a path of the project is found. Without it such an image
   * is shown by its caption only: a relative address means nothing to the browser.
   */
  resolveImage?: (path: string) => string
  /**
   * Mark every piece of the page with where it comes from in the source, so that a selection
   * can be turned into a range of the source (see `lib/sourceMap.ts`).
   */
  positions?: boolean
  /** Places after blocks of the text where the page shows something of its own. */
  slots?: Slot[]
  renderSlot?: (ids: string[]) => ReactNode
}

const ABSOLUTE = /^([a-z][a-z0-9+.-]*:|\/\/|\/|#)/i

/**
 * Read-only rendering of Markdown written by the agent: GitHub-flavoured Markdown with
 * mathematics in LaTeX (`$...$` inline, `$$...$$` displayed). Raw HTML in the source is not
 * rendered, and link protocols are limited to the safe ones by react-markdown.
 */
export function Markdown({
  source,
  className,
  resolveImage,
  positions = false,
  slots,
  renderSlot,
}: MarkdownProps) {
  // Slots are placed on the tree as written, positions are marked next, and formulas are
  // rendered last, inside their marks.
  const rehypePlugins = useMemo(() => {
    if (!positions && !slots?.length) return REHYPE_PLUGINS
    const plugins: NonNullable<Options["rehypePlugins"]> = []
    if (slots?.length) plugins.push([rehypeSlots, { slots }])
    if (positions) plugins.push(rehypeSourcePositions)
    return [...plugins, KATEX, HIGHLIGHT]
  }, [positions, slots])
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={rehypePlugins}
        components={{
          div: (given) => {
            // `node` is the syntax tree's own: it is not an attribute of the element.
            const props: Record<string, unknown> = { ...given }
            delete props.node
            const ids = props["data-slot"]
            return typeof ids === "string" && renderSlot ? (
              <div data-slot={ids}>{renderSlot(ids.split(" "))}</div>
            ) : (
              <div {...props} />
            )
          },
          img: ({ src, alt }) => {
            const address = typeof src === "string" ? src : ""
            if (!address) return null
            if (ABSOLUTE.test(address)) return <img src={address} alt={alt ?? ""} loading="lazy" />
            if (!resolveImage) return <span className="text-muted-foreground">[{alt || address}]</span>
            // Spans, not a figure element: Markdown puts an image inside a paragraph.
            return (
              <span className="md-figure">
                <img src={resolveImage(address)} alt={alt ?? ""} loading="lazy" />
                {alt && <span className="md-caption">{alt}</span>}
              </span>
            )
          },
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  )
}
