import { useId, useState, type FormEvent, type KeyboardEvent } from "react"
import type { AgentSession, PermissionMode } from "@/api/client"
import { useUpdateAgentSession } from "@/api/queries"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { PERMISSION_MODES } from "@/lib/agent"

interface ComposerProps {
  projectId: string
  session: AgentSession
  /** The session is still answering: one turn at a time. */
  busy: boolean
  /** Why nothing can be sent now, if so; shown as it is. */
  blocked: string | null
  onSend: (content: string) => void
  onError: (error: unknown) => void
}

/** Where a prompt is written, with the permission mode of the conversation beside it. */
export function Composer({ projectId, session, busy, blocked, onSend, onError }: ComposerProps) {
  const id = useId()
  const [content, setContent] = useState("")
  const update = useUpdateAgentSession(projectId, session.id)
  const mode = PERMISSION_MODES.find((item) => item.value === session.permission_mode)
  const disabled = busy || blocked !== null

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = content.trim()
    if (!text || disabled) return
    onSend(text)
    setContent("")
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.currentTarget.form?.requestSubmit()
    }
  }

  function changeMode(value: PermissionMode) {
    update.mutate({ version: session.version, permission_mode: value }, { onError })
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded-lg border border-border bg-card p-3">
      <label htmlFor={`${id}-prompt`} className="sr-only">
        Message to the agent
      </label>
      <Textarea
        id={`${id}-prompt`}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={keyDown}
        placeholder={
          busy
            ? "The agent is still answering; wait for it to end."
            : "Ask about the project, its code, its theory… (Ctrl+Enter sends)"
        }
        rows={3}
        disabled={disabled}
        maxLength={200_000}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <label htmlFor={`${id}-mode`}>Permission mode</label>
          <NativeSelect
            id={`${id}-mode`}
            size="sm"
            className="w-36"
            value={session.permission_mode}
            onChange={(event) => changeMode(event.target.value as PermissionMode)}
            disabled={busy || update.isPending}
          >
            {PERMISSION_MODES.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          {mode && <span>{mode.description}</span>}
        </div>
        <Button type="submit" disabled={disabled || !content.trim()}>
          Send
        </Button>
      </div>
      {blocked && (
        <p role="status" className="text-sm text-amber-800">
          {blocked}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Every turn is a call to Claude Code on your account; what it cost is shown on the answer.
      </p>
    </form>
  )
}
