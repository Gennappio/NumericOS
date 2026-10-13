import { Link } from "react-router"
import type { DocumentOut } from "@/api/client"
import { GenerateForm } from "@/components/documents/GenerateForm"
import { formatTimestamp } from "@/lib/time"

interface DocumentFooterProps {
  projectId: string
  document: DocumentOut
  /** What the document is, in a word: "theory", "pipeline". */
  name: string
  /** What asking for it again is called: on the fold ("Write it again") and on its button. */
  again: string
  action: string
  blocked: string | null
  pending: boolean
  onGenerate: (instructions: string) => void
}

/**
 * Under a document the agent wrote: which version it is and who wrote it, the files it was
 * written from (with the ones that changed since), and the request to write it again, which
 * starts from the instructions of the last one.
 */
export function DocumentFooter({
  projectId,
  document,
  name,
  again,
  action,
  blocked,
  pending,
  onGenerate,
}: DocumentFooterProps) {
  const changed = new Set(document.changed_sources ?? [])
  return (
    <footer className="space-y-3 rounded-lg border border-border bg-muted/30 p-4 text-sm">
      <p className="text-muted-foreground">
        Version {document.version}
        {document.model && <> · written by {document.model}</>}
        {document.generated_at && <> · {formatTimestamp(document.generated_at)}</>}
        {document.session_id && (
          <>
            {" · "}
            <Link
              to={`/projects/${projectId}/conversations/${document.session_id}`}
              className="underline underline-offset-4"
            >
              the agent&apos;s work
            </Link>
          </>
        )}
      </p>
      <details>
        <summary className="cursor-pointer text-muted-foreground">
          Written from {document.sources.length}{" "}
          {document.sources.length === 1 ? "file" : "files"} of the project
        </summary>
        {document.sources.length === 0 ? (
          <p className="mt-2 text-muted-foreground">
            The agent recorded no file it read: nothing can tell when this goes out of date.
          </p>
        ) : (
          <ul aria-label={`Files the ${name} was written from`} className="mt-2 space-y-0.5">
            {document.sources.map((source) => (
              <li key={source.path} className="font-mono text-xs break-all">
                {source.path}
                {changed.has(source.path) && (
                  <span className="ml-2 font-sans font-medium text-amber-800">changed since</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </details>
      <details open={document.stale}>
        <summary className="cursor-pointer text-muted-foreground">{again}</summary>
        <div className="mt-3">
          <GenerateForm
            action={action}
            instructions={document.instructions}
            blocked={blocked}
            pending={pending}
            onGenerate={onGenerate}
          />
        </div>
      </details>
    </footer>
  )
}
