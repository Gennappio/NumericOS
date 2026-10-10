import { ApiError, ApiUnreachableError } from "@/api/client"

/** A sentence a person can act on, for any error thrown by the API client. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "STALE_REVISION") {
      return "This item was changed elsewhere in the meantime. The view has been refreshed with the latest version; apply your change again."
    }
    if (error.code === "NOT_FOUND") return "This item no longer exists."
    return `${error.message} (${error.code})`
  }
  if (error instanceof ApiUnreachableError) {
    return `The NumericOS API is not reachable at ${error.url}. Nothing was saved.`
  }
  return "Unexpected error. Nothing was saved."
}

/** Per-field messages from a 422 envelope, keyed by the request field name. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.code !== "VALIDATION_ERROR") return {}
  const issues = error.details.errors
  if (!Array.isArray(issues)) return {}
  const result: Record<string, string> = {}
  for (const issue of issues as { loc?: unknown[]; msg?: unknown }[]) {
    const field = issue.loc?.at(-1)
    if (typeof field === "string" && typeof issue.msg === "string") result[field] = issue.msg
  }
  return result
}
