import { useId, useState } from "react"
import { Link } from "react-router"
import type { AgentSession, PermissionMode } from "@/api/client"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { PERMISSION_MODE_LABELS, PERMISSION_MODE_STYLES, PERMISSION_MODES } from "@/lib/agent"
import { formatTimestamp } from "@/lib/time"
import { cn } from "@/lib/utils"

interface SessionListProps {
  projectId: string
  sessions: AgentSession[]
  currentId: string | undefined
  disabled: boolean
  creating: boolean
  onCreate: (mode: PermissionMode) => void
}

/** The conversations of a project, newest first, and where a new one starts. */
export function SessionList({
  projectId,
  sessions,
  currentId,
  disabled,
  creating,
  onCreate,
}: SessionListProps) {
  const id = useId()
  const [mode, setMode] = useState<PermissionMode>("edit")
  return (
    <aside className="space-y-3">
      <div className="space-y-2 rounded-lg border border-border bg-card p-3">
        <Button className="w-full" onClick={() => onCreate(mode)} disabled={disabled || creating}>
          New conversation
        </Button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <label htmlFor={`${id}-mode`}>starting in mode</label>
          <NativeSelect
            id={`${id}-mode`}
            size="sm"
            className="w-36"
            value={mode}
            onChange={(event) => setMode(event.target.value as PermissionMode)}
            disabled={disabled}
          >
            {PERMISSION_MODES.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      </div>
      <nav aria-label="Conversations">
        {sessions.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">No conversation yet.</p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <Link
                  to={`/projects/${projectId}/agent/${session.id}`}
                  aria-current={session.id === currentId ? "page" : undefined}
                  className={cn(
                    "block rounded-md border px-3 py-2 text-sm",
                    session.id === currentId
                      ? "border-fuchsia-300 bg-fuchsia-50"
                      : "border-transparent hover:bg-muted",
                  )}
                >
                  <span className="line-clamp-2 break-words">{session.title}</span>
                  <span className="mt-1 block text-xs leading-6 text-muted-foreground">
                    <span
                      className={cn(
                        "rounded-full border px-1.5 py-0.5 font-medium",
                        PERMISSION_MODE_STYLES[session.permission_mode],
                      )}
                    >
                      {PERMISSION_MODE_LABELS[session.permission_mode]}
                    </span>{" "}
                    ·{" "}
                    {session.message_count === 1 ? "1 message" : `${session.message_count} messages`} ·{" "}
                    {formatTimestamp(session.updated_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </aside>
  )
}
