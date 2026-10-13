import { useId, useState, type FormEvent, type KeyboardEvent } from "react"
import type { AgentCapabilities, AgentPolicy, AgentSession, PermissionMode } from "@/api/client"
import { useUpdateAgentSession } from "@/api/queries"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import {
  PERMISSION_MODE_STYLES,
  PERMISSION_MODES,
  modelLabel,
  ownSetting,
  resolveChoice,
} from "@/lib/agent"
import { cn } from "@/lib/utils"

interface ComposerProps {
  projectId: string
  session: AgentSession
  policy: AgentPolicy | undefined
  capabilities: AgentCapabilities | undefined
  /** The session is still answering: one turn at a time. */
  busy: boolean
  /** Why nothing can be sent now, if so; shown as it is. */
  blocked: string | null
  onSend: (content: string) => void
  onError: (error: unknown) => void
}

/**
 * Where a prompt is written, with what the next turn will run with beside it: the permission
 * mode, and the model and effort (the policy's choice for this task, unless the conversation
 * overrides it).
 */
export function Composer({
  projectId,
  session,
  policy,
  capabilities,
  busy,
  blocked,
  onSend,
  onError,
}: ComposerProps) {
  const id = useId()
  const [content, setContent] = useState("")
  const update = useUpdateAgentSession(projectId, session.id)
  const mode = PERMISSION_MODES.find((item) => item.value === session.permission_mode)
  const disabled = busy || blocked !== null
  const models = capabilities?.models ?? []
  const efforts = capabilities?.efforts ?? []
  // What the policy gives this conversation: its task's row, else the project's default,
  // else the coding agent's own setting.
  const fromPolicy = resolveChoice(policy, session.task)
  const own = ownSetting(capabilities?.provider ?? policy?.provider)
  const settingsBusy = busy || update.isPending

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

  function change(patch: { permission_mode?: PermissionMode; model?: string | null; effort?: string | null }) {
    update.mutate({ version: session.version, ...patch }, { onError })
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
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <label htmlFor={`${id}-mode`}>Permission mode</label>
          <NativeSelect
            id={`${id}-mode`}
            size="sm"
            className="w-36"
            value={session.permission_mode}
            onChange={(event) => change({ permission_mode: event.target.value as PermissionMode })}
            disabled={settingsBusy}
          >
            {PERMISSION_MODES.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <label htmlFor={`${id}-model`}>Model</label>
          <NativeSelect
            id={`${id}-model`}
            size="sm"
            className="w-44"
            value={session.model ?? ""}
            onChange={(event) => change({ model: event.target.value || null })}
            disabled={settingsBusy || models.length === 0}
          >
            <NativeSelectOption value="">
              Policy: {fromPolicy.model ? modelLabel(fromPolicy.model, models) : own}
            </NativeSelectOption>
            {models.map((model) => (
              <NativeSelectOption key={model.id} value={model.id}>
                {model.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <label htmlFor={`${id}-effort`}>Effort</label>
          <NativeSelect
            id={`${id}-effort`}
            size="sm"
            className="w-36"
            value={session.effort ?? ""}
            onChange={(event) => change({ effort: event.target.value || null })}
            disabled={settingsBusy || efforts.length === 0}
          >
            <NativeSelectOption value="">
              Policy: {fromPolicy.effort ?? own}
            </NativeSelectOption>
            {efforts.map((effort) => (
              <NativeSelectOption key={effort} value={effort}>
                {effort}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <Button type="submit" disabled={disabled || !content.trim()}>
          Send
        </Button>
      </div>
      {mode && (
        <p className="text-xs text-muted-foreground">
          <span
            className={cn(
              "mr-1.5 rounded-full border px-1.5 py-0.5 font-medium",
              PERMISSION_MODE_STYLES[mode.value],
            )}
          >
            {mode.label}
          </span>
          {mode.description}
        </p>
      )}
      {blocked && (
        <p role="status" className="text-sm text-amber-800">
          {blocked}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Every turn uses your Claude account: what it consumed of your plan, and what it would
        cost at list prices, is shown on the answer.
      </p>
    </form>
  )
}
