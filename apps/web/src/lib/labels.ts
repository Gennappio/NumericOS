import type { CardType, WorkflowStatus } from "@/api/client"

// `Record` over the generated unions forces these maps to cover exactly the API vocabularies:
// a type or status added to the contract is a compile error here until it gets a label.

export const CARD_TYPE_LABELS: Record<CardType, string> = {
  task: "Task",
  hypothesis: "Hypothesis",
  experiment: "Experiment",
  issue: "Issue",
  decision: "Decision",
}
export const CARD_TYPES = Object.keys(CARD_TYPE_LABELS) as CardType[]

/** Workflow status is operational progress. It never states whether a result is valid. */
export const STATUS_LABELS: Record<WorkflowStatus, string> = {
  backlog: "Backlog",
  planned: "Planned",
  active: "Active",
  review: "Review",
  completed: "Completed",
  blocked: "Blocked",
}

/** Hues tell the kinds of card apart. None is green or red: a type never signals validity. */
export const CARD_TYPE_STYLES: Record<CardType, string> = {
  task: "border-slate-300 bg-slate-100 text-slate-800",
  hypothesis: "border-violet-300 bg-violet-100 text-violet-900",
  experiment: "border-sky-300 bg-sky-100 text-sky-900",
  issue: "border-orange-300 bg-orange-100 text-orange-900",
  decision: "border-pink-300 bg-pink-100 text-pink-900",
}
