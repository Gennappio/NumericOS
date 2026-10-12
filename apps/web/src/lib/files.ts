import type { FileCategory, FileEntry } from "@/api/client"

// `Record` over the generated union: a category added to the contract is a compile error here
// until it has a label.

export const CATEGORY_LABELS: Record<FileCategory, string> = {
  code: "Code",
  input: "Input",
  output: "Output",
  data: "Data",
  image: "Image",
  config: "Config",
  documentation: "Documentation",
  other: "Other",
}

/** A colour per kind of file: the tag, and the icon beside the name. */
export const CATEGORY_STYLES: Record<FileCategory, string> = {
  code: "border-sky-300 bg-sky-100 text-sky-900",
  input: "border-violet-300 bg-violet-100 text-violet-900",
  output: "border-pink-300 bg-pink-100 text-pink-900",
  data: "border-cyan-300 bg-cyan-100 text-cyan-900",
  image: "border-orange-300 bg-orange-100 text-orange-900",
  config: "border-amber-300 bg-amber-100 text-amber-900",
  documentation: "border-teal-300 bg-teal-100 text-teal-900",
  other: "border-slate-300 bg-slate-100 text-slate-700",
}

export const CATEGORY_ICON_TINTS: Record<FileCategory, string> = {
  code: "text-sky-600",
  input: "text-violet-600",
  output: "text-pink-600",
  data: "text-cyan-600",
  image: "text-orange-500",
  config: "text-amber-600",
  documentation: "text-teal-600",
  other: "text-slate-500",
}

export const CATEGORIES = Object.keys(CATEGORY_LABELS) as FileCategory[]

/** What is known about the description of a file, in one word. */
export type DescriptionState = "none" | "pending" | "failed" | "stale" | "described"

export function descriptionState(file: FileEntry): DescriptionState {
  const description = file.description
  if (!description) return "none"
  if (description.pending) return "pending"
  if (description.status === "failed") return "failed"
  if (description.stale) return "stale"
  return "described"
}

export const STATE_LABELS: Record<DescriptionState, string> = {
  none: "Not described",
  pending: "Being described",
  failed: "Not described: failed",
  stale: "Changed since",
  described: "Described",
}

/** Whether a description exists and is current: a fact about the description, not the file. */
export const STATE_STYLES: Record<DescriptionState, string> = {
  none: "border-slate-300 bg-white text-slate-600",
  pending: "border-sky-300 bg-sky-100 text-sky-900",
  failed: "border-red-300 bg-red-100 text-red-900",
  stale: "border-amber-400 bg-amber-100 text-amber-900",
  described: "border-emerald-300 bg-emerald-100 text-emerald-900",
}

/** The directory of a path, and its name in it. */
export function splitPath(path: string): { directory: string; name: string } {
  const cut = path.lastIndexOf("/")
  return cut < 0
    ? { directory: "", name: path }
    : { directory: path.slice(0, cut), name: path.slice(cut + 1) }
}

/** Files by directory, directories in the order of their paths, the root first. */
export function groupByDirectory(files: FileEntry[]): { directory: string; files: FileEntry[] }[] {
  const groups = new Map<string, FileEntry[]>()
  for (const file of files) {
    const { directory } = splitPath(file.path)
    const group = groups.get(directory)
    if (group) group.push(file)
    else groups.set(directory, [file])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([directory, grouped]) => ({ directory, files: grouped }))
}
