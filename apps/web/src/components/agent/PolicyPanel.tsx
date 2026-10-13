import { useId, useState } from "react"
import type { AgentCapabilities, AgentPolicy, AgentTask, TaskPolicy } from "@/api/client"
import { usePutAgentPolicy } from "@/api/queries"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { modelLabel, ownSetting, providerName, TASKS } from "@/lib/agent"
import { formatTimestamp } from "@/lib/time"

interface PolicyPanelProps {
  projectId: string
  policy: AgentPolicy
  capabilities: AgentCapabilities | undefined
  disabled: boolean
  onError: (error: unknown) => void
}

interface Draft {
  defaults: TaskPolicy
  tasks: Record<string, TaskPolicy>
}

const same = (a: TaskPolicy | undefined, b: TaskPolicy | undefined) =>
  (a?.model ?? null) === (b?.model ?? null) && (a?.effort ?? null) === (b?.effort ?? null)

/**
 * Which coding agent works on the project, and which model and effort it uses: one default
 * for every task, and a row per kind of task for the ones that should differ. A task left on
 * "Default" takes the default; the default, left on the agent's own setting, leaves the
 * choice to the agent, and the panel says what that was last seen to be.
 * Mount it keyed by the policy version: a saved policy starts a fresh draft.
 */
export function PolicyPanel({ projectId, policy, capabilities, disabled, onError }: PolicyPanelProps) {
  const id = useId()
  const [draft, setDraft] = useState<Draft>({ defaults: policy.defaults, tasks: policy.tasks })
  const save = usePutAgentPolicy(projectId)
  const models = capabilities?.models ?? []
  const efforts = capabilities?.efforts ?? []
  const provider = capabilities?.provider ?? policy.provider
  const own = ownSetting(provider)
  const seen = policy.provider_default
  const changed =
    !same(draft.defaults, policy.defaults) ||
    TASKS.some((task) => !same(draft.tasks[task.value], policy.tasks[task.value]))
  const choosing = TASKS.filter(
    (task) => policy.available.includes(task.value) && !same(draft.tasks[task.value], {}),
  )

  function setDefault(field: "model" | "effort", value: string) {
    setDraft({ ...draft, defaults: { ...draft.defaults, [field]: value || null } })
  }

  function setTask(task: AgentTask, field: "model" | "effort", value: string) {
    const row = { ...(draft.tasks[task] ?? {}), [field]: value || null }
    setDraft({ ...draft, tasks: { ...draft.tasks, [task]: row } })
  }

  /** Every task that is in use goes back to the default. */
  function followDefault() {
    const cleared = Object.fromEntries(
      policy.available.map((task) => [task, { model: null, effort: null }]),
    )
    setDraft({ ...draft, tasks: { ...draft.tasks, ...cleared } })
  }

  // What "Default" means on a task's row, as the draft stands: seen before it is saved.
  const defaultModel = draft.defaults.model ? modelLabel(draft.defaults.model, models) : own
  const defaultEffort = draft.defaults.effort ?? own

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <p className="text-sm" data-testid="coding-agent">
        <span className="font-medium">Coding agent:</span> {providerName(provider)}
        {/* The command prints its number and then its own name again: the number is enough. */}
        {capabilities?.version && <> {capabilities.version.split(" ")[0]}</>}{" "}
        {capabilities?.path && (
          <span className="font-mono text-xs break-all text-muted-foreground">
            {capabilities.path}
          </span>
        )}
        <span className="block text-xs text-muted-foreground">
          The only coding agent NumericOS drives today; another one will be chosen here.
        </span>
      </p>

      <table className="w-full text-sm" aria-label="Models and effort per task">
        <colgroup>
          <col />
          <col className="w-[38%]" />
          <col className="w-[26%]" />
        </colgroup>
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="pb-2 font-medium">Task</th>
            <th className="pb-2 font-medium">Model</th>
            <th className="pb-2 font-medium">Effort</th>
          </tr>
        </thead>
        <tbody>
          <tr data-task="default" className="bg-indigo-50/70">
            <th scope="row" className="rounded-l-md py-2 pr-3 pl-2 text-left align-top font-normal">
              <span className="font-semibold text-indigo-950">Default</span>
              <span className="block text-xs text-muted-foreground">
                What every task runs with, unless its own row chooses otherwise.
              </span>
            </th>
            <td className="py-2 pr-3 align-top">
              <NativeSelect
                id={`${id}-default-model`}
                aria-label="Default model"
                size="sm"
                className="w-full"
                value={draft.defaults.model ?? ""}
                onChange={(event) => setDefault("model", event.target.value)}
                disabled={disabled || models.length === 0}
              >
                <NativeSelectOption value="">
                  {own}
                  {seen && ` (last seen: ${modelLabel(seen.model, models)})`}
                </NativeSelectOption>
                {models.map((model) => (
                  <NativeSelectOption key={model.id} value={model.id}>
                    {model.label}
                    {model.note && ` — ${model.note}`}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </td>
            <td className="rounded-r-md py-2 pr-2 align-top">
              <NativeSelect
                id={`${id}-default-effort`}
                aria-label="Default effort"
                size="sm"
                className="w-full"
                value={draft.defaults.effort ?? ""}
                onChange={(event) => setDefault("effort", event.target.value)}
                disabled={disabled || efforts.length === 0}
              >
                <NativeSelectOption value="">{own}</NativeSelectOption>
                {efforts.map((effort) => (
                  <NativeSelectOption key={effort} value={effort}>
                    {effort}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </td>
          </tr>
          {TASKS.map((task) => {
            const available = policy.available.includes(task.value)
            const choice: TaskPolicy = draft.tasks[task.value] ?? {}
            return (
              <tr key={task.value} data-task={task.value} data-available={available}>
                <th scope="row" className="py-1.5 pr-3 pl-2 text-left align-top font-normal">
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
                    onChange={(event) => setTask(task.value, "model", event.target.value)}
                    disabled={disabled || !available || models.length === 0}
                  >
                    <NativeSelectOption value="">Default ({defaultModel})</NativeSelectOption>
                    {models.map((model) => (
                      <NativeSelectOption key={model.id} value={model.id}>
                        {model.label}
                        {model.note && ` — ${model.note}`}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </td>
                <td className="py-1.5 pr-2 align-top">
                  <NativeSelect
                    id={`${id}-${task.value}-effort`}
                    aria-label={`Effort for ${task.label}`}
                    size="sm"
                    className="w-full"
                    value={choice.effort ?? ""}
                    onChange={(event) => setTask(task.value, "effort", event.target.value)}
                    disabled={disabled || !available || efforts.length === 0}
                  >
                    <NativeSelectOption value="">Default ({defaultEffort})</NativeSelectOption>
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

      <div className="space-y-1.5 text-xs text-muted-foreground" data-testid="policy-explained">
        <p>
          <span className="font-medium text-foreground">{own}</span> leaves the choice to{" "}
          {providerName(provider)}: the model and the effort it uses when you start it yourself
          in a terminal. NumericOS neither reads nor changes that setting.{" "}
          {seen ? (
            <>
              The last turn that ran on it{seen.in_project ? " here" : ", in another project,"} was
              answered by{" "}
              <span className="font-medium text-foreground">{modelLabel(seen.model, models)}</span>{" "}
              (<span className="font-mono">{seen.model}</span>, {formatTimestamp(seen.seen_at)}).
            </>
          ) : (
            <>No turn ran on it yet, so which model that is has not been seen.</>
          )}{" "}
          The effort it uses is not reported.
        </p>
        <p>A conversation can override its row from the composer.</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || choosing.length === 0}
          title="Clear the choice of every task: they all run with the default"
          onClick={followDefault}
        >
          Leave every task on Default
        </Button>
        <Button
          size="sm"
          disabled={disabled || !changed || save.isPending}
          onClick={() =>
            save.mutate(
              { version: policy.version, tasks: draft.tasks, defaults: draft.defaults },
              { onError },
            )
          }
        >
          Save
        </Button>
      </div>
    </div>
  )
}
