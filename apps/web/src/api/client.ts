import type { components } from "./schema"

export type HealthOut = components["schemas"]["HealthOut"]
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"]
type ErrorBody = ErrorEnvelope["error"]

const DEFAULT_API_URL = "http://127.0.0.1:8765"

/** Base URL of the NumericOS API; `VITE_API_URL` overrides it at build/dev time. */
export const API_URL = (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "")

/** The API answered with its JSON error envelope. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly correlationId: string | null

  constructor(status: number, body: ErrorBody) {
    super(body.message)
    this.name = "ApiError"
    this.status = status
    this.code = body.code
    this.details = body.details ?? {}
    this.correlationId = body.correlation_id ?? null
  }
}

/** No HTTP response at all: the backend process is down or the URL is wrong. */
export class ApiUnreachableError extends Error {
  readonly url: string

  constructor(url: string, cause: unknown) {
    super(`Backend unreachable at ${url}`, { cause })
    this.name = "ApiUnreachableError"
    this.url = url
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  headers.set("X-Actor", "web:local")
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch (cause) {
    throw new ApiUnreachableError(API_URL, cause)
  }

  if (response.ok) {
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
  }
  throw new ApiError(response.status, await readErrorBody(response))
}

async function readErrorBody(response: Response): Promise<ErrorBody> {
  try {
    const envelope = (await response.json()) as Partial<ErrorEnvelope>
    if (envelope.error?.code && typeof envelope.error.message === "string") {
      return envelope.error
    }
  } catch {
    // not JSON: fall through to the generic body below
  }
  return {
    code: "HTTP_ERROR",
    message: `${response.status} ${response.statusText}`.trim(),
    details: {},
    correlation_id: response.headers.get("x-correlation-id"),
  }
}

export const fetchHealth = () => apiFetch<HealthOut>("/v1/health")
