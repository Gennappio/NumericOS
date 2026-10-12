import type {
  AgentTask,
  Message,
  MessageStatus,
  ModelChoice,
  PermissionMode,
  PlanUsage,
  TurnUsage,
} from "@/api/client"
import { formatSeconds } from "@/lib/format"

// `Record` over the generated unions: a status or mode added to the contract is a compile error
// here until it has a label.

/** How a turn of the agent stands or ended. "Answered" is an operational fact, not a verdict. */
export const TURN_STATUS_LABELS: Record<MessageStatus, string> = {
  queued: "Queued",
  running: "Working",
  final: "Answered",
  failed: "Failed",
  cancelled: "Stopped",
  interrupted: "Interrupted",
}

export const TURN_STATUS_STYLES: Record<MessageStatus, string> = {
  queued: "border-slate-300 bg-slate-100 text-slate-800",
  running: "border-sky-300 bg-sky-100 text-sky-900",
  final: "border-indigo-300 bg-indigo-100 text-indigo-900",
  failed: "border-red-300 bg-red-100 text-red-900",
  cancelled: "border-amber-300 bg-amber-100 text-amber-900",
  interrupted: "border-purple-300 bg-purple-100 text-purple-900",
}

export const TURN_STATUS_HINTS: Record<MessageStatus, string> = {
  queued: "Waiting for a supervisor to start the agent.",
  running: "The agent is working; its actions appear as they are recorded.",
  final: "The agent ended its turn with this answer.",
  failed: "The agent ended its turn with an error.",
  cancelled: "Stopped on request.",
  interrupted: "The agent process ended without a final answer.",
}

/** What each permission mode lets the agent do, in the words the composer shows. */
export const PERMISSION_MODES: { value: PermissionMode; label: string; description: string }[] = [
  {
    value: "read_only",
    label: "Read only",
    description: "The agent reads the repository. Edits and commands are refused.",
  },
  {
    value: "edit",
    label: "Edit files",
    description: "The agent may edit files. Commands it tries to run are refused.",
  },
  {
    value: "full",
    label: "Full autonomy",
    description: "The agent may edit files and run commands, as in a terminal with every permission skipped.",
  },
]

export const PERMISSION_MODE_LABELS: Record<PermissionMode, string> = Object.fromEntries(
  PERMISSION_MODES.map((mode) => [mode.value, mode.label]),
) as Record<PermissionMode, string>

/** The kinds of task the agent is used for; each has its own model and effort in the policy. */
export const TASKS: { value: AgentTask; label: string; description: string }[] = [
  { value: "conversation", label: "Conversation", description: "Questions asked in the conversations of the project." },
  {
    value: "clarify",
    label: "Clarify",
    description: "Clarifications asked on commented passages of an answer.",
  },
  { value: "resolve", label: "Resolve", description: "Change requests sent together." },
  { value: "theory", label: "Theory page", description: "The theory of the project as a paper." },
  {
    value: "file_description",
    label: "File descriptions",
    description: "One description per file of the project; many small turns.",
  },
  {
    value: "execution_description",
    label: "Execution description",
    description: "What happens when the program runs.",
  },
  { value: "plan", label: "Plan", description: "The plan of the agent as a board." },
]

/**
 * What a turn would cost at the provider's list prices, as the provider reports it. With a
 * subscription nothing is charged per turn: the figure measures the tokens used.
 */
export function formatListCost(usd: number): string {
  const shown = usd >= 1 ? usd.toFixed(2) : String(Number(usd.toPrecision(2)))
  return `${shown} USD at list prices`
}

export function formatTokens(usage: TurnUsage): string {
  const cached = usage.cache_read_input_tokens ?? 0
  const base = `${usage.input_tokens ?? 0} in / ${usage.output_tokens ?? 0} out tokens`
  return cached > 0 ? `${base} (+${cached.toLocaleString()} read from cache)` : base
}

/** Use of the plan's windows as the provider last reported it during the turn. */
export function formatPlanUsage(usage: PlanUsage): string {
  const parts: string[] = []
  if (usage.five_hour) parts.push(`${Math.round(usage.five_hour.utilization * 100)}% of the 5-hour window`)
  if (usage.seven_day) parts.push(`${Math.round(usage.seven_day.utilization * 100)}% of the week`)
  if (parts.length === 0) return ""
  return `plan: ${parts.join(", ")}${usage.using_overage ? " (overage in use)" : ""}`
}

/** The label of a model the provider offers, or its name as given. */
export function modelLabel(id: string | null | undefined, models: ModelChoice[]): string {
  if (!id) return "provider default"
  return models.find((choice) => choice.id === id)?.label ?? id
}

/** How long the agent worked on a turn, once it has both ends. */
export function turnDuration(message: Message): string | null {
  if (!message.started_at || !message.finished_at) return null
  const seconds = (Date.parse(message.finished_at) - Date.parse(message.started_at)) / 1000
  return seconds >= 0 ? formatSeconds(seconds) : null
}

/**
 * How much a permission mode lets the agent do to the project, as a colour: reading changes
 * nothing, editing changes files, full autonomy also runs commands.
 */
export const PERMISSION_MODE_STYLES: Record<PermissionMode, string> = {
  read_only: "border-emerald-300 bg-emerald-100 text-emerald-900",
  edit: "border-amber-300 bg-amber-100 text-amber-900",
  full: "border-rose-300 bg-rose-100 text-rose-900",
}

/** A colour per family of tool: looking, changing, running, the rest. */
export function toolStyle(name: string): string {
  if (["Read", "Grep", "Glob", "WebFetch", "WebSearch"].includes(name)) {
    return "bg-sky-100 text-sky-900"
  }
  if (["Edit", "Write", "MultiEdit", "NotebookEdit"].includes(name)) {
    return "bg-amber-100 text-amber-900"
  }
  if (name === "Bash") return "bg-violet-100 text-violet-900"
  return "bg-slate-100 text-slate-800"
}
