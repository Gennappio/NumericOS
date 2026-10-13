import type { ReactNode } from "react"
import type { DocumentOut } from "@/api/client"
import { formatTimestamp } from "@/lib/time"

interface ExportShellProps {
  /** The project the document is about, and what kind of document it is ("Pipeline"). */
  project: string
  what: string
  document: DocumentOut
  /** When the file was made. */
  exportedAt: string
  /** Wide for a board, a reading measure for a text. */
  wide?: boolean
  children: ReactNode
}

/**
 * The page a document is shared as: whose it is and what it is, the document, and under it
 * where it comes from. It says so when the code has changed since the document was written:
 * whoever receives the file cannot see that anywhere else.
 */
export function ExportShell({ project, what, document, exportedAt, wide, children }: ExportShellProps) {
  const changed = document.changed_sources ?? []
  return (
    <div
      className={
        wide ? "export-page mx-auto max-w-[110rem] px-6 py-8" : "export-page mx-auto max-w-5xl px-6 py-8"
      }
    >
      <p className="mb-4 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {project} · {what}
      </p>
      {document.stale && (
        <p className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <span className="font-medium">
            {changed.length === 1
              ? "A file this was written from has changed since:"
              : `${changed.length} files this was written from have changed since:`}
          </span>{" "}
          <span className="font-mono text-xs break-all">{changed.join(", ")}</span>. What follows
          describes the project as it was.
        </p>
      )}
      {children}
      <footer className="mt-8 border-t border-border pt-3 text-xs text-muted-foreground">
        Version {document.version}
        {document.model && <> · written by {document.model}</>}
        {document.generated_at && <> on {formatTimestamp(document.generated_at)}</>}
        {document.sources.length > 0 && (
          <>
            {" "}
            from {document.sources.length} {document.sources.length === 1 ? "file" : "files"} of
            the project
          </>
        )}
        {" · "}exported from NumericOS on {formatTimestamp(exportedAt)}.
      </footer>
    </div>
  )
}
