import type { CoverageLevel, FailureClass, RunStatus } from "@/api/client"

// `Record` over the generated unions: a status or class added to the contract is a compile
// error here until it has a label.

/**
 * A status says how the process of a run ended, never whether its result is valid. That is why
 * `succeeded` is worded as what it is, and is not shown in green.
 */
export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  starting: "Starting",
  running: "Running",
  succeeded: "Ended normally",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  lost: "Lost",
}

export const RUN_STATUS_STYLES: Record<RunStatus, string> = {
  queued: "border-slate-300 bg-slate-100 text-slate-800",
  starting: "border-slate-300 bg-slate-100 text-slate-800",
  running: "border-sky-300 bg-sky-100 text-sky-900",
  succeeded: "border-slate-400 bg-white text-slate-900",
  failed: "border-red-300 bg-red-100 text-red-900",
  cancelled: "border-amber-300 bg-amber-100 text-amber-900",
  timed_out: "border-red-300 bg-red-100 text-red-900",
  lost: "border-purple-300 bg-purple-100 text-purple-900",
}

/** What a status means, for someone who sees it for the first time. */
export const RUN_STATUS_HINTS: Record<RunStatus, string> = {
  queued: "Waiting for a supervisor to start it.",
  starting: "A supervisor is preparing the code and building the program.",
  running: "The program is running.",
  succeeded: "The program ended by itself with exit code 0. This says nothing about its result.",
  failed: "The program did not end normally.",
  cancelled: "Stopped on request.",
  timed_out: "Stopped because it passed its wall-clock limit.",
  lost: "Its monitor and its program are gone and nothing recorded how it ended.",
}

export const FAILURE_CLASS_LABELS: Record<FailureClass, string> = {
  code_error: "Code error",
  resource_limit: "Resource limit",
  numerical_instability: "Numerical instability",
  data_problem: "Data problem",
  infrastructure: "Infrastructure",
  unknown: "Unknown cause",
}

type CoverageStatus = CoverageLevel["status"]

export const COVERAGE_LABELS: Record<CoverageStatus, string> = {
  observed: "Observed",
  partial: "Partly observed",
  waiting: "Waiting",
  missing: "Missing",
  not_configured: "Not configured",
}

/** No green here either: "observed" means data exists, not that it is right. */
export const COVERAGE_STYLES: Record<CoverageStatus, string> = {
  observed: "border-sky-300 bg-sky-100 text-sky-900",
  partial: "border-amber-300 bg-amber-100 text-amber-900",
  waiting: "border-slate-300 bg-slate-100 text-slate-800",
  missing: "border-red-300 bg-red-100 text-red-900",
  not_configured: "border-slate-300 bg-white text-slate-600",
}

/** `{name: value}` parameters in the order the run recorded them. */
export function formatParameters(parameters: Record<string, unknown>): string {
  const entries = Object.entries(parameters)
  return entries.length === 0 ? "no parameters" : entries.map(([name, value]) => `${name}=${String(value)}`).join("  ")
}
