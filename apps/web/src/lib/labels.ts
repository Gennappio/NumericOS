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

/**
 * A colour per kind of card, as on a board with coloured labels: the tag is solid, the card
 * carries the colour on its edge and as a light tint. None is green or red: a type never
 * signals validity.
 */
export const CARD_TYPE_STYLES: Record<CardType, string> = {
  task: "border-sky-600 bg-sky-600 text-white",
  hypothesis: "border-violet-600 bg-violet-600 text-white",
  experiment: "border-cyan-600 bg-cyan-600 text-white",
  issue: "border-orange-600 bg-orange-600 text-white",
  decision: "border-pink-600 bg-pink-600 text-white",
}

export const CARD_TYPE_ACCENTS: Record<CardType, string> = {
  task: "border-l-sky-500 bg-sky-50",
  hypothesis: "border-l-violet-500 bg-violet-50",
  experiment: "border-l-cyan-500 bg-cyan-50",
  issue: "border-l-orange-500 bg-orange-50",
  decision: "border-l-pink-500 bg-pink-50",
}

/**
 * A colour per column: how far the work is. Completed is green and Blocked red as on any
 * Kanban board; they are about the work, and the line above the board says that a finished
 * card is not a confirmed result.
 */
export const STATUS_STYLES: Record<WorkflowStatus, { column: string; dot: string; count: string }> = {
  backlog: {
    column: "border-t-slate-400 bg-slate-100/80",
    dot: "bg-slate-400",
    count: "bg-slate-200 text-slate-700",
  },
  planned: {
    column: "border-t-indigo-400 bg-indigo-50",
    dot: "bg-indigo-500",
    count: "bg-indigo-100 text-indigo-800",
  },
  active: {
    column: "border-t-sky-500 bg-sky-50",
    dot: "bg-sky-500",
    count: "bg-sky-100 text-sky-800",
  },
  review: {
    column: "border-t-amber-500 bg-amber-50",
    dot: "bg-amber-500",
    count: "bg-amber-100 text-amber-900",
  },
  completed: {
    column: "border-t-emerald-500 bg-emerald-50",
    dot: "bg-emerald-500",
    count: "bg-emerald-100 text-emerald-800",
  },
  blocked: {
    column: "border-t-rose-500 bg-rose-50",
    dot: "bg-rose-500",
    count: "bg-rose-100 text-rose-800",
  },
}
