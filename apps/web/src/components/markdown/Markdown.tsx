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

/**
 * Read-only rendering of Markdown written by the agent: GitHub-flavoured Markdown with
 * mathematics in LaTeX (`$...$` inline, `$$...$$` displayed). Raw HTML in the source is not
 * rendered, and link protocols are limited to the safe ones by react-markdown.
 */
export function Markdown({ source, className }: { source: string; className?: string }) {
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS}>
        {source}
      </ReactMarkdown>
    </div>
  )
}
