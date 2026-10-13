import type { ReactNode } from "react"
import type { DocumentOut } from "@/api/client"

/**
 * Shown above a document one of whose files changed since it was written: which files, and
 * what to make of the text meanwhile (`children`). Nothing for a document that is current.
 */
export function StaleNotice({ document, children }: { document: DocumentOut; children: ReactNode }) {
  const changed = document.changed_sources ?? []
  if (!document.stale) return null
  return (
    <div
      role="alert"
      className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
    >
      <p className="font-medium">
        {changed.length === 1
          ? "A file this was written from has changed since."
          : `${changed.length} files this was written from have changed since.`}
      </p>
      <p className="mt-1 font-mono text-xs break-all">{changed.join(", ")}</p>
      <p className="mt-1">{children}</p>
    </div>
  )
}
