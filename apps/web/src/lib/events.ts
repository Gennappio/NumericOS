import type { EventOut, WorkflowStatus } from "@/api/client"
import { STATUS_LABELS } from "@/lib/labels"

type Fields = Record<string, unknown>

const FIELD_LABELS: Record<string, string> = {
  name: "name",
  research_question: "research question",
  description: "description",
  root_path: "code reference",
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
    default:
      return event.type
  }
}
