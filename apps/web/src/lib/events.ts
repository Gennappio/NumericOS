import type { EventOut, MessageStatus, RunStatus, WorkflowStatus } from "@/api/client"
import { TURN_STATUS_LABELS } from "@/lib/agent"
import { formatNumber, formatValue } from "@/lib/format"
import { STATUS_LABELS } from "@/lib/labels"
import { RUN_STATUS_LABELS } from "@/lib/runs"

type Fields = Record<string, unknown>

const FIELD_LABELS: Record<string, string> = {
  name: "name",
  research_question: "research question",
  description: "description",
  root_path: "code path",
  type: "type",
  title: "title",
  entity_ref: "linked entity",
}

function fields(value: unknown): Fields | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Fields)
    : undefined
}

function statusLabel(value: unknown): string {
  if (typeof value !== "string") return "an unknown column"
  return value in STATUS_LABELS ? STATUS_LABELS[value as WorkflowStatus] : value
}

function changedFields(value: unknown): string {
  if (!Array.isArray(value)) return ""
  return value
    .filter((field): field is string => typeof field === "string")
    .map((field) => FIELD_LABELS[field] ?? field)
    .join(", ")
}

/**
 * One line saying what a recorded event is, built only from the event's own type and payload.
 * An event type this GUI does not know is shown by its recorded name, never interpreted.
 */
export function describeEvent(event: EventOut): string {
  const card = fields(event.payload.card)
  const subject = typeof card?.title === "string" ? `"${card.title}"` : event.subject_id
  const changed = changedFields(event.payload.changed_fields)

  switch (event.type) {
    case "PROJECT_CREATED":
      return "Project created"
    case "PROJECT_UPDATED":
      return changed ? `Project updated: ${changed}` : "Project updated"
    case "CARD_CREATED":
      return `Card created: ${subject} in ${statusLabel(card?.workflow_status)}`
    case "CARD_UPDATED":
      return changed ? `Card edited: ${subject} (${changed})` : `Card edited: ${subject}`
    case "CARD_MOVED": {
      const from = statusLabel(fields(event.payload.from)?.workflow_status)
      const to = statusLabel(fields(event.payload.to)?.workflow_status)
      const move =
        from === to
          ? `Card reordered: ${subject} in ${to}`
          : `Card moved: ${subject} from ${from} to ${to}`
      return changed ? `${move}, edited ${changed}` : move
    }
    case "PROJECT_EXECUTION_TRUSTED":
      return "Execution allowed in the project directory"
    case "PROJECT_EXECUTION_TRUST_REVOKED":
      return "Execution in the project directory no longer allowed"
    case "HYPOTHESIS_CREATED":
      return `Hypothesis stated: ${named(event.payload.hypothesis, "title")}`
    case "HYPOTHESIS_UPDATED":
      return `Hypothesis reworded: ${named(event.payload.hypothesis, "title")}`
    case "EXPERIMENT_CREATED":
      return `Experiment defined: ${named(event.payload.experiment, "name")}`
    case "EXPERIMENT_UPDATED":
      return `Experiment changed: ${named(event.payload.experiment, "name")}`
    default:
      return describeRunEvent(event) ?? describeAgentEvent(event) ?? event.type
  }
}

/** What an event of a conversation with the agent says, from its own payload. */
function describeAgentEvent(event: EventOut): string | undefined {
  const payload = event.payload
  switch (event.type) {
    case "AGENT_SESSION_STARTED":
      return "Conversation with the agent opened"
    case "AGENT_SESSION_UPDATED": {
      const changed = changedFields(payload.changed_fields)
      return changed ? `Conversation changed: ${changed}` : "Conversation changed"
    }
    case "AGENT_TURN_QUEUED":
      return typeof payload.prompt_excerpt === "string"
        ? `Agent asked: "${payload.prompt_excerpt}"`
        : "Agent asked"
    case "AGENT_TURN_STARTED":
      return `Agent working (process ${text(payload.pid)})`
    case "AGENT_TURN_FINISHED": {
      const status = text(payload.status) as MessageStatus
      const label = status in TURN_STATUS_LABELS ? TURN_STATUS_LABELS[status] : status
      const reason = typeof payload.status_reason === "string" ? `: ${payload.status_reason}` : ""
      return `Agent turn ended, ${label.toLowerCase()}${reason}`
    }
    case "AGENT_TURN_CANCEL_REQUESTED":
      return `Stop requested: ${text(payload.reason)}`
    case "AGENT_POLICY_UPDATED":
      return "Models and effort per task changed"
    case "DOCUMENT_GENERATION_QUEUED":
      return `Agent asked for ${documentWords(payload.kind, payload.keys)}`
    case "DOCUMENT_GENERATION_FINISHED": {
      const written = Array.isArray(payload.written) ? payload.written : []
      const failed = fields(payload.failed) ?? {}
      const failures = Object.keys(failed).length
      if (payload.kind === "plan" && written.length > 0) {
        return `Plan of the agent put on the board: ${text(payload.cards_created)} card(s) added, ${text(payload.cards_changed)} changed`
      }
      if (written.length === 0) {
        return `Agent did not write ${documentWords(payload.kind, Object.keys(failed))}: ${String(Object.values(failed)[0] ?? "no reason recorded")}`
      }
      const rest = failures > 0 ? `; ${failures} not written` : ""
      return `Agent wrote ${documentWords(payload.kind, written)}${rest}`
    }
    case "ANNOTATION_CREATED":
      return `Comment added: ${commentWords(payload.annotation)}`
    case "ANNOTATION_UPDATED":
      return `Comment changed: ${commentWords(payload.annotation)}`
    case "ANNOTATIONS_SENT": {
      const count = Array.isArray(payload.annotation_ids) ? payload.annotation_ids.length : 0
      return payload.task === "resolve"
        ? `Resolve: ${count} change request(s) sent to the agent`
        : `Clarify: ${count} clarification request(s) sent to the agent`
    }
    case "ANNOTATIONS_ANSWERED": {
      const answered = Array.isArray(payload.answered) ? payload.answered.length : 0
      const reopened = Object.keys(fields(payload.reopened) ?? {}).length
      const rest = reopened > 0 ? `; ${reopened} not answered` : ""
      if (payload.task === "resolve") {
        const rewritten =
          typeof payload.document_version === "number"
            ? `; the text is now version ${payload.document_version}`
            : ""
        return `Resolve: ${text(payload.applied)} applied, ${text(payload.declined)} declined${rewritten}${rest}`
      }
      return `Clarify: ${answered} answered${rest}`
    }
    case "AGENT_TURN_ADOPTED":
      return "Another supervisor took the agent turn over"
    case "AGENT_TURN_REQUEUED":
      return "Agent turn queued again: its supervisor stopped before starting the agent"
    default:
      return undefined
  }
}

/** "the theory", "the plan", "the description of solver.py", "the descriptions of 8 files". */
function documentWords(kind: unknown, keys: unknown): string {
  if (kind === "theory") return "the theory"
  if (kind === "plan") return "a plan"
  const paths = Array.isArray(keys) ? keys : []
  return paths.length === 1
    ? `the description of ${String(paths[0])}`
    : `the descriptions of ${paths.length} files`
}

/** "clarification on “…passage…”" for a comment as the ledger keeps it. */
function commentWords(value: unknown): string {
  const comment = fields(value)
  const quote = typeof comment?.quote === "string" ? comment.quote.replace(/\s+/g, " ") : ""
  const passage = quote.length > 60 ? `${quote.slice(0, 59)}…` : quote
  const kind = comment?.kind === "change" ? "change request" : text(comment?.kind)
  const status = comment?.status === "dismissed" ? ", withdrawn" : ""
  return `${kind} on “${passage}”${status}`
}

function named(value: unknown, field: string): string {
  const name = fields(value)?.[field]
  return typeof name === "string" ? `"${name}"` : "unnamed"
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "?"
}

function atStep(payload: Fields): string {
  return typeof payload.step === "number" ? ` at step ${payload.step}` : ""
}

/**
 * What an event of a run says, from its own payload. The words describe what was recorded: a
 * run that "ended normally" is not thereby called valid.
 */
function describeRunEvent(event: EventOut): string | undefined {
  const payload = event.payload
  switch (event.type) {
    case "RUN_QUEUED":
      return "Run queued"
    case "RUN_STARTED":
      return `Program started (process ${text(payload.pid)})`
    case "RUN_FINISHED": {
      const status = text(payload.status) as RunStatus
      const label = status in RUN_STATUS_LABELS ? RUN_STATUS_LABELS[status] : status
      const reason = typeof payload.status_reason === "string" ? `: ${payload.status_reason}` : ""
      return `Run ended, ${label.toLowerCase()}${reason}`
    }
    case "RUN_CANCEL_REQUESTED":
      return `Stop requested: ${text(payload.reason)}`
    case "RUN_LIMIT_EXCEEDED":
      return `Limit passed: ${text(payload.limit)} reached ${formatMeasure(payload.value)}, allowed ${formatMeasure(payload.threshold)}`
    case "RUN_OUTPUT_TRUNCATED":
      return "Output beyond the limit of the contract is no longer stored"
    case "RUN_METRICS_TRUNCATED":
      return "Metric samples beyond the limit of the contract are no longer stored"
    case "RUN_LEFTOVER_PROCESSES":
      return "The program left processes behind; they were stopped"
    case "RUN_SOURCE_CHANGED":
      return "The source was edited while the program ran"
    case "RUN_ADOPTED":
      return "Another supervisor took the run over"
    case "RUN_REQUEUED":
      return "Queued again: its supervisor stopped before starting the program"
    case "RUN_MONITOR_LOST":
      return "The monitor is gone while the program still runs: its end will not be recorded"
    case "RUN_METRIC_NON_FINITE":
      return `Metric ${text(payload.metric)} became ${formatValue(null, text(payload.value))}${atStep(payload)}`
    case "RUN_GUARDRAIL_VIOLATED": {
      const value =
        typeof payload.value === "number"
          ? formatNumber(payload.value)
          : formatValue(null, typeof payload.non_finite === "string" ? payload.non_finite : null)
      const consequence = payload.action === "halt" ? "the program was stopped" : "recorded only"
      return `Guardrail: ${text(payload.metric)} ${text(payload.bound)} ${formatMeasure(payload.threshold)} for ${text(payload.consecutive)} consecutive samples (${value}${atStep(payload)}); ${consequence}`
    }
    case "RUN_PROGRAM_EVENT": {
      const message = typeof payload.message === "string" && payload.message ? `: ${payload.message}` : ""
      return `Program: ${text(payload.name)}${message}${atStep(payload)}`
    }
    default:
      return undefined
  }
}

function formatMeasure(value: unknown): string {
  return typeof value === "number" ? formatNumber(value) : "?"
}
