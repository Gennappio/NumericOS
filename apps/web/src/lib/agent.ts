import type { Message, MessageStatus, PermissionMode } from "@/api/client"
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
  final: "border-slate-400 bg-white text-slate-900",
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

/** A cost in US dollars with the digits that matter at its size. */
export function formatCost(usd: number): string {
  const shown = usd >= 1 ? usd.toFixed(2) : String(Number(usd.toPrecision(2)))
  return `${shown} USD`
}

/** How long the agent worked on a turn, once it has both ends. */
export function turnDuration(message: Message): string | null {
  if (!message.started_at || !message.finished_at) return null
  const seconds = (Date.parse(message.finished_at) - Date.parse(message.started_at)) / 1000
  return seconds >= 0 ? formatSeconds(seconds) : null
}
