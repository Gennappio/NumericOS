import ReactMarkdown from "react-markdown"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import "katex/dist/katex.min.css"
import { remarkDisplayDollars } from "@/components/markdown/displayMath"
import { cn } from "@/lib/utils"

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkDisplayDollars]
// A formula KaTeX cannot parse is shown as its source in red, never thrown.
const REHYPE_PLUGINS: [typeof rehypeKatex, { throwOnError: boolean; strict: string }][] = [
  [rehypeKatex, { throwOnError: false, strict: "ignore" }],
]

interface MarkdownProps {
  source: string
  className?: string
  /**
   * Where an image whose address is a path of the project is found. Without it such an image
   * is shown by its caption only: a relative address means nothing to the browser.
   */
  resolveImage?: (path: string) => string
}

const ABSOLUTE = /^([a-z][a-z0-9+.-]*:|\/\/|\/|#)/i

/**
 * Read-only rendering of Markdown written by the agent: GitHub-flavoured Markdown with
 * mathematics in LaTeX (`$...$` inline, `$$...$$` displayed). Raw HTML in the source is not
 * rendered, and link protocols are limited to the safe ones by react-markdown.
 */
export function Markdown({ source, className, resolveImage }: MarkdownProps) {
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={{
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
