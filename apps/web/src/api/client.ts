import type { components } from "./schema"

type Schemas = components["schemas"]
export type HealthOut = Schemas["HealthOut"]
export type ErrorEnvelope = Schemas["ErrorEnvelope"]
export type Project = Schemas["ProjectOut"]
export type ProjectList = Schemas["ProjectList"]
export type ProjectCreate = Schemas["ProjectCreate"]
export type ProjectPatch = Schemas["ProjectPatch"]
export type Card = Schemas["CardOut"]
export type CardCreate = Schemas["CardCreate"]
export type CardPatch = Schemas["CardPatch"]
export type Board = Schemas["BoardOut"]
export type CardType = Schemas["CardType"]
export type WorkflowStatus = Schemas["WorkflowStatus"]
export type EventOut = Schemas["EventOut"]
export type EventPage = Schemas["EventPage"]
export type ExecutionTrust = Schemas["ExecutionTrust"]
export type Experiment = Schemas["ExperimentOut"]
export type ExperimentList = Schemas["ExperimentList"]
export type ExperimentProtocol = Schemas["ExperimentProtocol"]
export type ExperimentSeries = Schemas["ExperimentSeries"]
export type ExperimentSeriesList = Schemas["ExperimentSeriesList"]
export type ContractFile = Schemas["ContractFile"]
export type ContractFileList = Schemas["ContractFileList"]
export type ContractImport = Schemas["ContractImport"]
export type Run = Schemas["RunOut"]
export type RunList = Schemas["RunList"]
export type RunCreate = Schemas["RunCreate"]
export type RunStatus = Schemas["RunStatus"]
export type FailureClass = Schemas["FailureClass"]
export type CodeProvenance = Schemas["CodeProvenance"]
export type RunMetrics = Schemas["RunMetrics"]
export type SeriesSummary = Schemas["SeriesSummary"]
export type Coverage = Schemas["Coverage"]
export type CoverageLevel = Schemas["CoverageLevel"]
export type MetricCoverage = Schemas["MetricCoverage"]
export type Diagnostic = Schemas["Diagnostic"]
export type MetricOverview = Schemas["MetricOverview"]
export type MetricBucket = Schemas["MetricBucket"]
export type LogLine = Schemas["LogLine"]
export type LogPage = Schemas["LogPage"]
export type ResourceSample = Schemas["ResourceSample"]
export type ResourcePage = Schemas["ResourcePage"]
export type Artifact = Schemas["ArtifactOut"]
export type ArtifactList = Schemas["ArtifactList"]
export type WorkerList = Schemas["WorkerList"]
export type AgentSession = Schemas["AgentSessionOut"]
export type AgentSessionList = Schemas["AgentSessionList"]
export type AgentSessionCreate = Schemas["AgentSessionCreate"]
export type AgentSessionPatch = Schemas["AgentSessionPatch"]
export type PermissionMode = Schemas["PermissionMode"]
export type Message = Schemas["MessageOut"]
export type MessageList = Schemas["MessageList"]
export type MessageStatus = Schemas["MessageStatus"]
export type ActivityItem = Schemas["ActivityItem"]
export type AgentCapabilities = Schemas["AgentCapabilities"]
export type ModelChoice = Schemas["ModelChoice"]
export type PlanUsage = Schemas["PlanUsage"]
export type TurnUsage = Schemas["TurnUsage"]
export type AgentTask = Schemas["AgentTask"]
export type TaskPolicy = Schemas["TaskPolicy"]
export type AgentPolicy = Schemas["AgentPolicyOut"]
export type AgentPolicyPut = Schemas["AgentPolicyPut"]
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

const send = (method: "POST" | "PATCH", body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
})
const seg = encodeURIComponent

/** Where a reading by cursor starts: at a cursor, or at the last `tail` records. */
export type CursorStart = { after: number } | { tail: number }

function cursorQuery(start: CursorStart, limit: number): string {
  const position = "after" in start ? `after=${start.after}` : `tail=${start.tail}`
  return `${position}&limit=${limit}`
}

/** One function per API operation; names follow the operation IDs of the contract. */
export const api = {
  health: () => apiFetch<HealthOut>("/v1/health"),
  listProjects: () => apiFetch<ProjectList>("/v1/projects"),
  getProject: (projectId: string) => apiFetch<Project>(`/v1/projects/${seg(projectId)}`),
  createProject: (body: ProjectCreate) => apiFetch<Project>("/v1/projects", send("POST", body)),
  updateProject: (projectId: string, body: ProjectPatch) =>
    apiFetch<Project>(`/v1/projects/${seg(projectId)}`, send("PATCH", body)),
  getBoard: (projectId: string) => apiFetch<Board>(`/v1/projects/${seg(projectId)}/board`),
  createCard: (projectId: string, body: CardCreate) =>
    apiFetch<Card>(`/v1/projects/${seg(projectId)}/cards`, send("POST", body)),
  updateCard: (cardId: string, body: CardPatch) =>
    apiFetch<Card>(`/v1/cards/${seg(cardId)}`, send("PATCH", body)),
  /** The newest entries of a project's ledger, newest first. */
  listRecentEvents: (projectId: string, limit: number) =>
    apiFetch<EventPage>(`/v1/events?project_id=${seg(projectId)}&order=desc&limit=${limit}`),

  trustExecution: (projectId: string, body: ExecutionTrust) =>
    apiFetch<Project>(`/v1/projects/${seg(projectId)}:trust-execution`, send("POST", body)),
  listContractFiles: (projectId: string) =>
    apiFetch<ContractFileList>(`/v1/projects/${seg(projectId)}/contract-files`),
  importExperiment: (projectId: string, body: ContractImport) =>
    apiFetch<Experiment>(`/v1/projects/${seg(projectId)}/experiments:import`, send("POST", body)),
  listExperiments: (projectId: string) =>
    apiFetch<ExperimentList>(`/v1/projects/${seg(projectId)}/experiments`),
  getExperiment: (experimentId: string) =>
    apiFetch<Experiment>(`/v1/experiments/${seg(experimentId)}`),
  listExperimentRuns: (experimentId: string) =>
    apiFetch<RunList>(`/v1/experiments/${seg(experimentId)}/runs`),
  listExperimentSeries: (experimentId: string) =>
    apiFetch<ExperimentSeriesList>(`/v1/experiments/${seg(experimentId)}/series`),
  listProjectRuns: (projectId: string, limit: number) =>
    apiFetch<RunList>(`/v1/projects/${seg(projectId)}/runs?limit=${limit}`),
  /** The key makes a repeated submission (a double click, a retry) return the same run. */
  createRun: (experimentId: string, body: RunCreate, idempotencyKey: string) =>
    apiFetch<Run>(`/v1/experiments/${seg(experimentId)}/runs`, {
      ...send("POST", body),
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  getRun: (runId: string) => apiFetch<Run>(`/v1/runs/${seg(runId)}`),
  cancelRun: (runId: string, reason: string) =>
    apiFetch<Run>(`/v1/runs/${seg(runId)}:cancel`, send("POST", { reason })),
  /** A new run with the same commit, parameters and seed. */
  rerun: (runId: string, idempotencyKey: string) =>
    apiFetch<Run>(`/v1/runs/${seg(runId)}:rerun`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  getRunMetrics: (runId: string) => apiFetch<RunMetrics>(`/v1/runs/${seg(runId)}/metrics`),
  getMetricOverview: (runId: string, name: string, buckets: number) =>
    apiFetch<MetricOverview>(
      `/v1/runs/${seg(runId)}/metrics/${seg(name)}/overview?buckets=${buckets}`,
    ),
  readLogs: (runId: string, start: CursorStart, limit: number) =>
    apiFetch<LogPage>(`/v1/runs/${seg(runId)}/logs?${cursorQuery(start, limit)}`),
  readResources: (runId: string, start: CursorStart, limit: number) =>
    apiFetch<ResourcePage>(`/v1/runs/${seg(runId)}/resources?${cursorQuery(start, limit)}`),
  listRunEvents: (runId: string) =>
    apiFetch<EventPage>(`/v1/runs/${seg(runId)}/events?limit=1000`),
  listArtifacts: (runId: string) => apiFetch<ArtifactList>(`/v1/runs/${seg(runId)}/artifacts`),
  listWorkers: () => apiFetch<WorkerList>("/v1/workers"),

  getAgentCapabilities: () => apiFetch<AgentCapabilities>("/v1/agents/capabilities"),
  listAgentSessions: (projectId: string) =>
    apiFetch<AgentSessionList>(`/v1/projects/${seg(projectId)}/agent-sessions`),
  createAgentSession: (projectId: string, body: AgentSessionCreate) =>
    apiFetch<AgentSession>(`/v1/projects/${seg(projectId)}/agent-sessions`, send("POST", body)),
  getAgentSession: (sessionId: string) =>
    apiFetch<AgentSession>(`/v1/agent-sessions/${seg(sessionId)}`),
  updateAgentSession: (sessionId: string, body: AgentSessionPatch) =>
    apiFetch<AgentSession>(`/v1/agent-sessions/${seg(sessionId)}`, send("PATCH", body)),
  listMessages: (sessionId: string) =>
    apiFetch<MessageList>(`/v1/agent-sessions/${seg(sessionId)}/messages`),
  /** The prompt is recorded and the answer queued: the returned message is the agent's turn. */
  sendMessage: (sessionId: string, content: string) =>
    apiFetch<Message>(`/v1/agent-sessions/${seg(sessionId)}/messages`, send("POST", { content })),
  getMessage: (messageId: string) => apiFetch<Message>(`/v1/messages/${seg(messageId)}`),
  cancelMessage: (messageId: string, reason: string) =>
    apiFetch<Message>(`/v1/messages/${seg(messageId)}:cancel`, send("POST", { reason })),
  getAgentPolicy: (projectId: string) =>
    apiFetch<AgentPolicy>(`/v1/projects/${seg(projectId)}/agent-policy`),
  putAgentPolicy: (projectId: string, body: AgentPolicyPut) =>
    apiFetch<AgentPolicy>(`/v1/projects/${seg(projectId)}/agent-policy`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
}

/** Download address of one file of a run. */
export function artifactUrl(artifactId: string): string {
  return `${API_URL}/v1/artifacts/${seg(artifactId)}/content`
}

/** The run with its provenance and protocol, as JSON: what is needed to repeat it. */
export function runRecordUrl(runId: string): string {
  return `${API_URL}/v1/runs/${seg(runId)}/record`
}

/** URL of the Server-Sent Events view of a project's ledger, starting after `cursor`. */
export function eventStreamUrl(projectId: string, cursor: number): string {
  return `${API_URL}/v1/events?project_id=${seg(projectId)}&after=${cursor}`
}
