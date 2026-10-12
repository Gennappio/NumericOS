import {
  ArrowDownToLineIcon,
  ArrowUpFromLineIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DatabaseIcon,
  FileCodeIcon,
  FileIcon,
  FileTextIcon,
  ImageIcon,
  SettingsIcon,
  type LucideIcon,
} from "lucide-react"
import { fileContentUrl, type FileCategory, type FileEntry } from "@/api/client"
import { useFileDescription } from "@/api/queries"
import { Commentable } from "@/components/comments/Commentable"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { describeError } from "@/lib/errors"
import {
  CATEGORY_ICON_TINTS,
  CATEGORY_LABELS,
  CATEGORY_STYLES,
  descriptionState,
  splitPath,
  STATE_LABELS,
  STATE_STYLES,
} from "@/lib/files"
import { formatBytes } from "@/lib/format"
import { formatTimestamp } from "@/lib/time"
import { cn } from "@/lib/utils"

const CATEGORY_ICONS: Record<FileCategory, LucideIcon> = {
  code: FileCodeIcon,
  input: ArrowDownToLineIcon,
  output: ArrowUpFromLineIcon,
  data: DatabaseIcon,
  image: ImageIcon,
  config: SettingsIcon,
  documentation: FileTextIcon,
  other: FileIcon,
}

interface FileRowProps {
  projectId: string
  file: FileEntry
  open: boolean
  onToggle: () => void
  /** Why the agent cannot be asked now, if so. */
  blocked: string | null
  supervisorAlive: boolean
  busy: boolean
  onDescribe: () => void
  onError: (error: unknown) => void
}

/**
 * One file of the project: what it is, how large, and what its description says in a
 * sentence. Opened, it shows the whole description, the image if it is one, and whether the
 * file has changed since the description was written.
 */
export function FileRow({
  projectId,
  file,
  open,
  onToggle,
  blocked,
  supervisorAlive,
  busy,
  onDescribe,
  onError,
}: FileRowProps) {
  const state = descriptionState(file)
  const { name } = splitPath(file.path)
  const Icon = CATEGORY_ICONS[file.category]
  return (
    <li data-path={file.path} data-state={state} className="border-t border-border first:border-t-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        {open ? (
          <ChevronDownIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRightIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Icon
              aria-hidden="true"
              className={cn("size-4 shrink-0", CATEGORY_ICON_TINTS[file.category])}
            />
            <span className="font-mono text-[0.8125rem] break-all">{name}</span>
            <Badge variant="outline" className={CATEGORY_STYLES[file.category]}>
              {CATEGORY_LABELS[file.category]}
            </Badge>
            <span className="text-xs text-muted-foreground">{formatBytes(file.size_bytes)}</span>
            <span
              className={cn(
                "inline-flex h-5 items-center gap-1.5 rounded-full border px-2 text-xs font-medium",
                STATE_STYLES[state],
              )}
            >
              {state === "pending" && (
                <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-current" />
              )}
              {STATE_LABELS[state]}
            </span>
          </span>
          {file.description?.summary && (
            <span className="mt-0.5 block text-sm text-muted-foreground">
              {file.description.summary}
            </span>
          )}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border bg-muted/20 px-4 py-3 pl-9">
          {file.viewable_image && (
            <img
              src={fileContentUrl(projectId, file.path)}
              alt={file.path}
              loading="lazy"
              className="max-h-80 rounded border border-border bg-white"
            />
          )}
          {state === "stale" && (
            <p role="alert" className="text-sm text-amber-900">
              This file has changed since it was described: what follows is about its earlier
              content.
            </p>
          )}
          {state === "failed" && (
            <p role="alert" className="text-sm text-red-800">
              {file.description?.status_reason ?? "The agent returned no description."}
            </p>
          )}
          {file.description && file.description.status === "ready" ? (
            <Description
              projectId={projectId}
              path={file.path}
              updatedAt={file.description.updated_at}
              blocked={blocked}
              supervisorAlive={supervisorAlive}
              onError={onError}
            />
          ) : (
            state === "none" && (
              <p className="text-sm text-muted-foreground">The agent has not described this file.</p>
            )
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={blocked !== null || busy || state === "pending"}
              onClick={onDescribe}
            >
              {state === "described" || state === "stale" ? "Describe it again" : "Describe this file"}
            </Button>
            <span className="font-mono text-xs break-all text-muted-foreground">{file.path}</span>
          </div>
        </div>
      )}
    </li>
  )
}

function Description({
  projectId,
  path,
  updatedAt,
  blocked,
  supervisorAlive,
  onError,
}: {
  projectId: string
  path: string
  updatedAt: string
  blocked: string | null
  supervisorAlive: boolean
  onError: (error: unknown) => void
}) {
  const description = useFileDescription(projectId, path, updatedAt)
  if (description.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading the description…
      </p>
    )
  }
  if (description.isError) {
    return <p className="text-sm text-muted-foreground">{describeError(description.error)}</p>
  }
  const document = description.data
  return (
    <div className="space-y-2">
      <Commentable
        key={document.version}
        projectId={projectId}
        target={{ type: "document", id: document.id }}
        source={document.markdown}
        version={document.version}
        layout="below"
        blocked={blocked}
        supervisorAlive={supervisorAlive}
        onError={onError}
      />
      <p className="text-xs text-muted-foreground">
        Version {document.version}
        {document.model && <> · written by {document.model}</>}
        {document.generated_at && <> · {formatTimestamp(document.generated_at)}</>}
      </p>
    </div>
  )
}
