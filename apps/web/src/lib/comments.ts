import type { Annotation, AnnotationKind, AnnotationStatus } from "@/api/client"

// `Record` over the generated unions: a kind or status added to the contract is a compile
// error here until it has a label.

export const KIND_LABELS: Record<AnnotationKind, string> = {
  clarification: "Clarification",
  change: "Change request",
  note: "Note",
}

/** What the button of the selection toolbar says for each kind. */
export const KIND_ACTIONS: Record<AnnotationKind, string> = {
  clarification: "Ask to clarify",
  change: "Request a change",
  note: "Add a note",
}

export const KIND_PROMPTS: Record<AnnotationKind, string> = {
  clarification: "What is not clear about this passage?",
  change: "What should change: in the code, in this text, or in both?",
  note: "A note for yourself (the agent does not see it)",
}

/** A colour per kind of comment: its tag, the edge of its card, its highlight in the text. */
export const KIND_STYLES: Record<AnnotationKind, string> = {
  clarification: "border-sky-600 bg-sky-600 text-white",
  change: "border-orange-600 bg-orange-600 text-white",
  note: "border-violet-600 bg-violet-600 text-white",
}

export const KIND_ACCENTS: Record<AnnotationKind, string> = {
  clarification: "border-l-sky-500",
  change: "border-l-orange-500",
  note: "border-l-violet-500",
}

/** How a comment stands. "Clarified" and "Applied" say what the agent did, not that it is right. */
export const STATUS_STYLES: Record<AnnotationStatus, string> = {
  open: "bg-slate-100 text-slate-700",
  pending: "bg-sky-100 text-sky-800",
  answered: "bg-emerald-100 text-emerald-800",
  resolved: "bg-emerald-100 text-emerald-800",
  declined: "bg-rose-100 text-rose-800",
  dismissed: "bg-slate-100 text-slate-500",
}

export const STATUS_LABELS: Record<AnnotationStatus, string> = {
  open: "Open",
  pending: "With the agent",
  answered: "Clarified",
  resolved: "Applied",
  declined: "Declined by the agent",
  dismissed: "Withdrawn",
}

/** Names of the highlights (see `::highlight()` in index.css). */
export function highlightName(annotation: Annotation): string {
  if (annotation.status === "open" || annotation.status === "pending") {
    return `nos-${annotation.kind}`
  }
  return "nos-settled"
}

export const HIGHLIGHT_NAMES = [
  "nos-clarification",
  "nos-change",
  "nos-note",
  "nos-settled",
  "nos-focus",
  "nos-draft",
] as const

/** A passage in a line, for a list: its source with the white space collapsed. */
export function excerpt(quote: string, limit = 140): string {
  const line = quote.replace(/\s+/g, " ").trim()
  return line.length <= limit ? line : `${line.slice(0, limit - 1)}…`
}

export function countOpen(annotations: Annotation[], kind: AnnotationKind): number {
  return annotations.filter(
    (item) => item.kind === kind && item.status === "open" && item.anchor_state === "attached",
  ).length
}
