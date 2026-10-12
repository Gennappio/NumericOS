import { useId, useState } from "react"
import type { AgentCapabilities, AgentPolicy, AgentTask, TaskPolicy } from "@/api/client"
import { usePutAgentPolicy } from "@/api/queries"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { TASKS } from "@/lib/agent"

interface PolicyPanelProps {
  projectId: string
  policy: AgentPolicy
  capabilities: AgentCapabilities | undefined
  disabled: boolean
  onError: (error: unknown) => void
}

type Draft = Record<string, TaskPolicy>

/**
 * Which model and effort the agent uses for each kind of task of the project. The choices
 * offered are the provider's; a task whose feature is not built yet is shown, not editable.
 * Mount it keyed by the policy version: a saved policy starts a fresh draft.
 */
export function PolicyPanel({ projectId, policy, capabilities, disabled, onError }: PolicyPanelProps) {
  const id = useId()
  const [draft, setDraft] = useState<Draft>(policy.tasks)
  const save = usePutAgentPolicy(projectId)
  const models = capabilities?.models ?? []
  const efforts = capabilities?.efforts ?? []
  const changed = TASKS.some(
    (task) =>
      (draft[task.value]?.model ?? null) !== (policy.tasks[task.value]?.model ?? null) ||
      (draft[task.value]?.effort ?? null) !== (policy.tasks[task.value]?.effort ?? null),
  )

  function set(task: AgentTask, field: "model" | "effort", value: string) {
    setDraft({ ...draft, [task]: { ...(draft[task] ?? {}), [field]: value || null } })
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <table className="w-full text-sm" aria-label="Models and effort per task">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="pb-2 font-medium">Task</th>
            <th className="pb-2 font-medium">Model</th>
            <th className="pb-2 font-medium">Effort</th>
          </tr>
        </thead>
        <tbody>
          {TASKS.map((task) => {
            const available = policy.available.includes(task.value)
            const choice: TaskPolicy = draft[task.value] ?? {}
            return (
              <tr key={task.value} data-task={task.value} data-available={available}>
                <th scope="row" className="py-1.5 pr-3 text-left align-top font-normal">
                  <span className="font-medium">{task.label}</span>
                  <span className="block text-xs text-muted-foreground">
                    {available ? task.description : `${task.description} Not available yet.`}
                  </span>
                </th>
                <td className="py-1.5 pr-3 align-top">
                  <NativeSelect
                    id={`${id}-${task.value}-model`}
                    aria-label={`Model for ${task.label}`}
                    size="sm"
                    className="w-full"
                    value={choice.model ?? ""}
                    onChange={(event) => set(task.value, "model", event.target.value)}
                    disabled={disabled || !available || models.length === 0}
                  >
                    <NativeSelectOption value="">Provider default</NativeSelectOption>
                    {models.map((model) => (
                      <NativeSelectOption key={model.id} value={model.id}>
                        {model.label}
                        {model.note && ` — ${model.note}`}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </td>
                <td className="py-1.5 align-top">
                  <NativeSelect
                    id={`${id}-${task.value}-effort`}
                    aria-label={`Effort for ${task.label}`}
                    size="sm"
                    className="w-full"
                    value={choice.effort ?? ""}
                    onChange={(event) => set(task.value, "effort", event.target.value)}
                    disabled={disabled || !available || efforts.length === 0}
                  >
                    <NativeSelectOption value="">Provider default</NativeSelectOption>
                    {efforts.map((effort) => (
                      <NativeSelectOption key={effort} value={effort}>
                        {effort}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          "Provider default" leaves the choice to {capabilities?.provider === "claude_code" ? "Claude Code" : "the provider"}
          {" "}(its own settings). A conversation can override its row from the composer.
        </p>
        <Button
          size="sm"
          disabled={disabled || !changed || save.isPending}
          onClick={() =>
            save.mutate({ version: policy.version, tasks: draft }, { onError })
          }
        >
          Save
        </Button>
      </div>
    </div>
  )
}
