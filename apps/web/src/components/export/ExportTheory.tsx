import { Markdown } from "@/components/markdown/Markdown"

interface ExportTheoryProps {
  markdown: string
  resolveImage: (path: string) => string
}

/** The theory as it is read in the application: a paper, with its formulas and figures. */
export function ExportTheory({ markdown, resolveImage }: ExportTheoryProps) {
  return (
    <article className="export-sheet rounded-lg border border-border bg-card px-6 py-10 md:px-12">
      <Markdown source={markdown} className="paper" resolveImage={resolveImage} />
    </article>
  )
}
