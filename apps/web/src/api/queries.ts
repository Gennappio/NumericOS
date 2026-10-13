import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  api,
  type AgentPolicyPut,
  type AnnotationCreate,
  type AnnotationsSend,
  type CommentTarget,
  type AgentSessionCreate,
  type AgentSessionPatch,
  type CardCreate,
  type CardPatch,
  type ContractImport,
  type DescribeRequest,
  type Message,
  type MessageStatus,
  type ProjectPatch,
  type Run,
  type RunCreate,
  type RunStatus,
} from "./client"

export const queryKeys = {
  health: ["health"] as const,
  workers: ["workers"] as const,
  projects: ["projects"] as const,
  /**
   * Prefix of everything that belongs to one project: the project, its board, its events,
   * its experiments and its runs. An event of the project refreshes all of it.
   */
  project: (projectId: string) => ["projects", projectId] as const,
  board: (projectId: string) => ["projects", projectId, "board"] as const,
  events: (projectId: string) => ["projects", projectId, "events"] as const,
  contractFiles: (projectId: string) => ["projects", projectId, "contract-files"] as const,
  experiments: (projectId: string) => ["projects", projectId, "experiments"] as const,
  experiment: (projectId: string, experimentId: string) =>
    ["projects", projectId, "experiments", experimentId] as const,
  experimentRuns: (projectId: string, experimentId: string) =>
    ["projects", projectId, "experiments", experimentId, "runs"] as const,
  experimentSeries: (projectId: string, experimentId: string) =>
    ["projects", projectId, "experiments", experimentId, "series"] as const,
  projectRuns: (projectId: string) => ["projects", projectId, "runs"] as const,
  run: (projectId: string, runId: string) => ["projects", projectId, "runs", runId] as const,
  runMetrics: (projectId: string, runId: string) =>
    ["projects", projectId, "runs", runId, "metrics"] as const,
  metricOverview: (projectId: string, runId: string, name: string) =>
    ["projects", projectId, "runs", runId, "metrics", name] as const,
  runEvents: (projectId: string, runId: string) =>
    ["projects", projectId, "runs", runId, "events"] as const,
  artifacts: (projectId: string, runId: string) =>
    ["projects", projectId, "runs", runId, "artifacts"] as const,
  agentCapabilities: ["agents", "capabilities"] as const,
  agentPolicy: (projectId: string) => ["projects", projectId, "agent-policy"] as const,
  agentSessions: (projectId: string) => ["projects", projectId, "agent-sessions"] as const,
  agentSession: (projectId: string, sessionId: string) =>
    ["projects", projectId, "agent-sessions", sessionId] as const,
  messages: (projectId: string, sessionId: string) =>
    ["projects", projectId, "agent-sessions", sessionId, "messages"] as const,
  message: (projectId: string, messageId: string) =>
    ["projects", projectId, "messages", messageId] as const,
  workspace: (projectId: string) => ["projects", projectId, "workspace"] as const,
  theory: (projectId: string) => ["projects", projectId, "theory"] as const,
  pipeline: (projectId: string) => ["projects", projectId, "pipeline"] as const,
  plan: (projectId: string) => ["projects", projectId, "plan"] as const,
  files: (projectId: string) => ["projects", projectId, "files"] as const,
  fileDescription: (projectId: string, path: string) =>
    ["projects", projectId, "files", "description", path] as const,
  annotations: (projectId: string, target: CommentTarget) =>
    ["projects", projectId, "annotations", target.type, target.id] as const,
}

/**
 * Interval of bounded re-reads of real backend state. Used where no event stream exists (the
 * project list, health) and as the fallback of a project page whose stream is not live.
 */
export const POLL_MS = 5_000

/** How many of the newest ledger entries the event strip shows. */
export const RECENT_EVENTS = 20

/** Polls the API liveness endpoint; the result drives every "is the backend live?" indicator. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: POLL_MS,
    retry: 0,
    staleTime: 2_000,
  })
}

export type ConnectionState = "checking" | "connected" | "unreachable"

export interface ConnectionInfo {
  state: ConnectionState
  version?: string
  /** True when the API answers but reports a degraded database (e.g. pending migrations). */
  degraded?: boolean
  /** Epoch milliseconds of the last successful health check, if there was one. */
  lastContactAt?: number
}

/** Derived from the live health query: an error always wins over previously cached data. */
export function useConnectionState(): ConnectionInfo {
  const health = useHealth()
  const lastContactAt = health.dataUpdatedAt || undefined
  if (health.status === "error") return { state: "unreachable", lastContactAt }
  if (health.status === "success") {
    return {
      state: "connected",
      version: health.data.version,
      degraded: health.data.status === "degraded",
      lastContactAt,
    }
  }
  return { state: "checking" }
}

/** No project-independent event stream exists yet, so the list of projects is polled. */
export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: api.listProjects,
    refetchInterval: POLL_MS,
  })
}

// The queries of a project page take `live`: while the project's event stream is live every
// change arrives as an event and triggers a re-read, so polling is switched off.

export function useProject(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => api.getProject(projectId),
    refetchInterval: live ? false : POLL_MS,
  })
}

export function useBoard(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.board(projectId),
    queryFn: () => api.getBoard(projectId),
    refetchInterval: live ? false : POLL_MS,
  })
}

export function recentEventsQuery(projectId: string) {
  return queryOptions({
    queryKey: queryKeys.events(projectId),
    queryFn: () => api.listRecentEvents(projectId, RECENT_EVENTS),
  })
}

export function useRecentEvents(projectId: string, live: boolean) {
  return useQuery({ ...recentEventsQuery(projectId), refetchInterval: live ? false : POLL_MS })
}

// Mutations return the invalidation promise from `onSettled`: the mutation stays pending until
// the refreshed data (with the new record versions) is on screen, so a second action can never
// be sent with a stale version by accident.

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.createProject,
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: ProjectPatch) => api.updateProject(projectId, patch),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useCreateCard(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (card: CardCreate) => api.createCard(projectId, card),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useUpdateCard(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    // The project assertion makes the API refuse a card that belongs to another project.
    mutationFn: ({ cardId, patch }: { cardId: string; patch: CardPatch }) =>
      api.updateCard(cardId, { ...patch, project_id: projectId }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

// ---------------------------------------------------------------------------------------------
// Experiments and runs. Their state changes in two ways: through ledger events (queued,
// started, finished, ...), which the project's stream turns into a refresh, and silently while a
// program runs (new samples, new output). So what belongs to a run that may still change is
// also re-read at a short interval, and never once the run has ended.

/** How often what a running program produces is re-read. */
export const RUN_POLL_MS = 2_000

const ACTIVE_STATUSES: readonly RunStatus[] = ["queued", "starting", "running"]

/** The run may still change by itself. */
export function isActive(status: RunStatus | undefined): boolean {
  return status !== undefined && ACTIVE_STATUSES.includes(status)
}

export function useWorkers() {
  return useQuery({ queryKey: queryKeys.workers, queryFn: api.listWorkers, refetchInterval: POLL_MS })
}

export function useContractFiles(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.contractFiles(projectId),
    queryFn: () => api.listContractFiles(projectId),
    enabled,
  })
}

export function useExperiments(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.experiments(projectId),
    queryFn: () => api.listExperiments(projectId),
    refetchInterval: live ? false : POLL_MS,
  })
}

export function useExperiment(projectId: string, experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experiment(projectId, experimentId),
    queryFn: () => api.getExperiment(experimentId),
  })
}

const anyActive = (runs: Run[] | undefined) => runs?.some((run) => isActive(run.status)) ?? false

export function useExperimentRuns(projectId: string, experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experimentRuns(projectId, experimentId),
    queryFn: () => api.listExperimentRuns(experimentId),
    refetchInterval: (query) => (anyActive(query.state.data?.runs) ? RUN_POLL_MS : false),
  })
}

export function useExperimentSeries(projectId: string, experimentId: string, active: boolean) {
  return useQuery({
    queryKey: queryKeys.experimentSeries(projectId, experimentId),
    queryFn: () => api.listExperimentSeries(experimentId),
    refetchInterval: active ? RUN_POLL_MS : false,
  })
}

export function useProjectRuns(projectId: string, limit = 25) {
  return useQuery({
    queryKey: queryKeys.projectRuns(projectId),
    queryFn: () => api.listProjectRuns(projectId, limit),
    refetchInterval: (query) => (anyActive(query.state.data?.runs) ? RUN_POLL_MS : false),
  })
}

export function useRun(projectId: string, runId: string) {
  return useQuery({
    queryKey: queryKeys.run(projectId, runId),
    queryFn: () => api.getRun(runId),
    refetchInterval: (query) => (isActive(query.state.data?.status) ? RUN_POLL_MS : false),
  })
}

export function useRunMetrics(projectId: string, runId: string, active: boolean) {
  return useQuery({
    queryKey: queryKeys.runMetrics(projectId, runId),
    queryFn: () => api.getRunMetrics(runId),
    refetchInterval: active ? RUN_POLL_MS : false,
  })
}

/** How many buckets a chart asks for: more than its width in pixels would not be visible. */
export const CHART_BUCKETS = 300

export function useMetricOverview(projectId: string, runId: string, name: string, active: boolean) {
  return useQuery({
    queryKey: queryKeys.metricOverview(projectId, runId, name),
    queryFn: () => api.getMetricOverview(runId, name, CHART_BUCKETS),
    refetchInterval: active ? RUN_POLL_MS : false,
  })
}

export function useRunEvents(projectId: string, runId: string) {
  return useQuery({
    queryKey: queryKeys.runEvents(projectId, runId),
    queryFn: () => api.listRunEvents(runId),
  })
}

export function useArtifacts(projectId: string, runId: string) {
  return useQuery({
    queryKey: queryKeys.artifacts(projectId, runId),
    queryFn: () => api.listArtifacts(runId),
  })
}

export function useTrustExecution(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { version: number; root_path: string }) =>
      api.trustExecution(projectId, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useImportExperiment(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ContractImport) => api.importExperiment(projectId, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useCreateRun(projectId: string, experimentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ body, key }: { body: RunCreate; key: string }) =>
      api.createRun(experimentId, body, key),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useRerun(projectId: string, runId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.rerun(runId, key),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useCancelRun(projectId: string, runId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reason: string) => api.cancelRun(runId, reason),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.run(projectId, runId) }),
  })
}

// ---------------------------------------------------------------------------------------------
// Conversations with the agent. A turn changes through ledger events (queued, started, ended)
// and silently while the agent works (its actions are recorded as it goes), so the messages of
// a conversation with an active turn are re-read at the short interval, like a running run.

const ACTIVE_TURN_STATUSES: readonly MessageStatus[] = ["queued", "running"]

/** The turn may still change by itself. */
export function isTurnActive(status: MessageStatus | undefined): boolean {
  return status !== undefined && ACTIVE_TURN_STATUSES.includes(status)
}

const anyTurnActive = (messages: Message[] | undefined) =>
  messages?.some((message) => isTurnActive(message.status)) ?? false

/** Whether the agent command is installed: found by running it, re-checked now and then. */
export function useAgentCapabilities() {
  return useQuery({
    queryKey: queryKeys.agentCapabilities,
    queryFn: api.getAgentCapabilities,
    refetchInterval: POLL_MS * 6,
    staleTime: POLL_MS,
  })
}

export function useAgentPolicy(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.agentPolicy(projectId),
    queryFn: () => api.getAgentPolicy(projectId),
    refetchInterval: live ? false : POLL_MS,
  })
}

export function usePutAgentPolicy(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AgentPolicyPut) => api.putAgentPolicy(projectId, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.agentPolicy(projectId) }),
  })
}

/**
 * The conversations of a project, for the sidebar. The list of the project on screen is also
 * re-read at every event of its stream; the others have no stream and are polled slowly.
 */
export function useAgentSessions(projectId: string, open: boolean) {
  return useQuery({
    queryKey: queryKeys.agentSessions(projectId),
    queryFn: () => api.listAgentSessions(projectId),
    refetchInterval: open ? POLL_MS : POLL_MS * 6,
  })
}

export function useAgentSession(projectId: string, sessionId: string) {
  return useQuery({
    queryKey: queryKeys.agentSession(projectId, sessionId),
    queryFn: () => api.getAgentSession(sessionId),
  })
}

export function useMessages(projectId: string, sessionId: string) {
  return useQuery({
    queryKey: queryKeys.messages(projectId, sessionId),
    queryFn: () => api.listMessages(sessionId),
    refetchInterval: (query) =>
      anyTurnActive(query.state.data?.messages) ? RUN_POLL_MS : false,
  })
}

export function useCreateAgentSession(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AgentSessionCreate) => api.createAgentSession(projectId, body),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions(projectId) }),
  })
}

export function useUpdateAgentSession(projectId: string, sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: AgentSessionPatch) => api.updateAgentSession(sessionId, patch),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions(projectId) }),
  })
}

export function useSendMessage(projectId: string, sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => api.sendMessage(sessionId, content),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions(projectId) }),
  })
}

export function useCancelMessage(projectId: string, sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ messageId, reason }: { messageId: string; reason: string }) =>
      api.cancelMessage(messageId, reason),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.messages(projectId, sessionId) }),
  })
}

// ---------------------------------------------------------------------------------------------
// Documents the agent writes. While a turn is writing one, it is re-read at the short interval:
// its end arrives as a ledger event too, but the stream may not be live.

/** One turn of the agent, followed while it works: what a document in progress shows. */
export function useMessage(projectId: string, messageId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.message(projectId, messageId ?? ""),
    queryFn: () => api.getMessage(messageId!),
    enabled: Boolean(messageId),
    refetchInterval: (query) => (isTurnActive(query.state.data?.status) ? RUN_POLL_MS : false),
  })
}

export function useTheory(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.theory(projectId),
    queryFn: () => api.getTheory(projectId),
    refetchInterval: (query) =>
      query.state.data?.document?.pending_message_id ? RUN_POLL_MS : live ? false : POLL_MS,
  })
}

export function useGenerateTheory(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (instructions: string | undefined) => api.generateTheory(projectId, instructions),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.theory(projectId) }),
  })
}

export function usePipeline(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.pipeline(projectId),
    queryFn: () => api.getPipeline(projectId),
    refetchInterval: (query) =>
      query.state.data?.document?.pending_message_id ? RUN_POLL_MS : live ? false : POLL_MS,
  })
}

export function useGeneratePipeline(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (instructions: string | undefined) =>
      api.generatePipeline(projectId, instructions),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(projectId) }),
  })
}

export function usePlan(projectId: string, live: boolean) {
  return useQuery({
    queryKey: queryKeys.plan(projectId),
    queryFn: () => api.getPlan(projectId),
    refetchInterval: (query) =>
      query.state.data?.document?.pending_message_id ? RUN_POLL_MS : live ? false : POLL_MS,
  })
}

export function useGeneratePlan(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (instructions: string | undefined) => api.generatePlan(projectId, instructions),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.plan(projectId) }),
  })
}

export function useFiles(projectId: string, live: boolean, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.files(projectId),
    queryFn: () => api.listFiles(projectId),
    enabled,
    refetchInterval: (query) =>
      (query.state.data?.counts.generating ?? 0) > 0 ? RUN_POLL_MS : live ? false : POLL_MS,
  })
}

export function useDescribeFiles(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: DescribeRequest) => api.describeFiles(projectId, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.files(projectId) }),
  })
}

/** The whole description of one file; `version` makes a description written again a new read. */
export function useFileDescription(projectId: string, path: string, updatedAt: string) {
  return useQuery({
    queryKey: [...queryKeys.fileDescription(projectId, path), updatedAt],
    queryFn: () => api.getFileDescription(projectId, path),
  })
}

// ---------------------------------------------------------------------------------------------
// Comments on what the agent wrote. While a turn is answering some of them they are re-read at
// the short interval; when it ends, everything of the project is re-read once, because a
// Resolve may have rewritten the text and changed files.

export function useAnnotations(projectId: string, target: CommentTarget, enabled = true) {
  return useQuery({
    queryKey: queryKeys.annotations(projectId, target),
    queryFn: () => api.listAnnotations(target),
    enabled,
    refetchInterval: (query) => (query.state.data?.pending_message_id ? RUN_POLL_MS : false),
  })
}

export function useCreateAnnotation(projectId: string, target: CommentTarget) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<AnnotationCreate, "target_type" | "target_id">) =>
      api.createAnnotation({ ...body, target_type: target.type, target_id: target.id }),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.annotations(projectId, target) }),
  })
}

export function useDismissAnnotation(projectId: string, target: CommentTarget) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (annotationId: string) => api.dismissAnnotation(annotationId),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.annotations(projectId, target) }),
  })
}

export function useSendAnnotations(projectId: string, target: CommentTarget) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      action,
      ...options
    }: { action: "clarify" | "resolve" } & Omit<AnnotationsSend, "target_type" | "target_id">) => {
      const body = { ...options, target_type: target.type, target_id: target.id }
      return action === "clarify" ? api.clarifyAnnotations(body) : api.resolveAnnotations(body)
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.annotations(projectId, target) }),
  })
}

// ---------------------------------------------------------------------------------------------
// The NumericOS folder of a project, and what a turn left outside it.

export function useWorkspace(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.workspace(projectId),
    queryFn: () => api.getWorkspace(projectId),
    enabled,
  })
}

export function useMoveCreatedFiles(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (messageId: string) => api.moveCreatedFiles(messageId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}
