import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router"
import type { AgentCapabilities, PermissionMode } from "@/api/client"
import {
  isTurnActive,
  useAgentCapabilities,
  useAgentSession,
  useAgentSessions,
  useCancelMessage,
  useCreateAgentSession,
  useMessages,
  useSendMessage,
  useWorkers,
} from "@/api/queries"
import { Composer } from "@/components/agent/Composer"
import { MessageCard } from "@/components/agent/MessageCard"
import { SessionList } from "@/components/agent/SessionList"
import { ErrorPanel } from "@/components/ErrorPanel"
import { ExecutionPanel } from "@/components/experiments/ExecutionPanel"
import { Notice } from "@/components/Notice"
import { Section } from "@/components/Section"
import { describeError } from "@/lib/errors"
import { useProjectContext } from "@/pages/projectContext"

/**
 * Conversations with the coding agent about this project. The agent works in the project's
 * directory as you; the preconditions (the directory trusted, a supervisor alive, the agent
 * command installed) are shown as they are, never assumed.
 */
export function AgentView() {
  const { project, live, offline } = useProjectContext()
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const capabilities = useAgentCapabilities()
  const sessions = useAgentSessions(project.id, live)
  const workers = useWorkers()
  const create = useCreateAgentSession(project.id)
  const [notice, setNotice] = useState<string | null>(null)

  const trusted = Boolean(project.execution_trusted_at)
  const blocked = blockedBy(project.root_path, trusted, capabilities.data)
  const supervisorAlive = (workers.data?.alive ?? 0) > 0
  const currentId = sessionId ?? sessions.data?.sessions[0]?.id

  function startConversation(mode: PermissionMode) {
    create.mutate(
      { permission_mode: mode },
      {
        onSuccess: (session) => navigate(`/projects/${project.id}/agent/${session.id}`),
        onError: (error) => setNotice(describeError(error)),
      },
    )
  }

  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}

      {(blocked !== null || !supervisorAlive) && (
        <Section title="Before the agent can work">
          <div className="space-y-3">
            <ExecutionPanel project={project} disabled={offline} purpose="agent" />
            <AgentPanel capabilities={capabilities.data} error={capabilities.error} />
          </div>
        </Section>
      )}

      <div className="grid gap-5 md:grid-cols-[16rem_minmax(0,1fr)]">
        {sessions.isPending ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading conversations…
          </p>
        ) : sessions.isError ? (
          <ErrorPanel
            title="Could not load the conversations"
            error={sessions.error}
            onRetry={() => void sessions.refetch()}
          />
        ) : (
          <SessionList
            projectId={project.id}
            sessions={sessions.data.sessions}
            currentId={currentId}
            disabled={offline || blocked !== null}
            creating={create.isPending}
            onCreate={startConversation}
          />
        )}
        {currentId ? (
          <Conversation
            key={currentId}
            projectId={project.id}
            sessionId={currentId}
            supervisorAlive={supervisorAlive}
            blocked={offline ? "The NumericOS API is not reachable." : blocked}
            onError={(error) => setNotice(describeError(error))}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">
            Start a conversation to ask the agent about this project: what its code does, what
            theory it implements, what a result means.
          </div>
        )}
      </div>
    </div>
  )
}

/** Why nothing can be sent to the agent right now, if anything stands in the way. */
function blockedBy(
  rootPath: string | null,
  trusted: boolean,
  capabilities: AgentCapabilities | undefined,
): string | null {
  if (rootPath === null) return "This project has no code path: set it with Edit project."
  if (!trusted) return "Execution in the project directory is not allowed yet (see above)."
  if (capabilities && !capabilities.available) {
    return `The agent command is not available: ${capabilities.problem ?? "unknown reason"}`
  }
  return null
}

function AgentPanel({
  capabilities,
  error,
}: {
  capabilities: AgentCapabilities | undefined
  error: unknown
}) {
  return (
    <div
      data-state={capabilities ? (capabilities.available ? "available" : "unavailable") : "checking"}
      className="space-y-1 rounded-lg border border-border bg-card p-4"
    >
      <h3 className="text-sm font-medium">Coding agent</h3>
      {capabilities ? (
        capabilities.available ? (
          <p className="text-sm">
            Claude Code {capabilities.version}{" "}
            <span className="font-mono text-xs break-all text-muted-foreground">
              {capabilities.path}
            </span>
          </p>
        ) : (
          <p className="text-sm">
            <span className="font-medium text-amber-800">Not available.</span>{" "}
            {capabilities.problem}
          </p>
        )
      ) : error ? (
        <p className="text-sm text-muted-foreground">{describeError(error)}</p>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          Checking…
        </p>
      )}
    </div>
  )
}

interface ConversationProps {
  projectId: string
  sessionId: string
  supervisorAlive: boolean
  blocked: string | null
  onError: (error: unknown) => void
}

function Conversation({ projectId, sessionId, supervisorAlive, blocked, onError }: ConversationProps) {
  const session = useAgentSession(projectId, sessionId)
  const messages = useMessages(projectId, sessionId)
  const send = useSendMessage(projectId, sessionId)
  const cancel = useCancelMessage(projectId, sessionId)
  const end = useRef<HTMLDivElement>(null)
  const list = messages.data?.messages ?? []
  const busy = list.some((message) => isTurnActive(message.status))

  // A new message, or a turn that moved, is at the bottom: keep it in view.
  const lastStatus = list.length ? `${list.length}:${list[list.length - 1].status}` : ""
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" })
  }, [lastStatus])

  if (session.isPending || messages.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading the conversation…
      </p>
    )
  }
  if (session.isError || messages.isError) {
    return (
      <ErrorPanel
        title="Could not load the conversation"
        error={session.error ?? messages.error}
        onRetry={() => {
          void session.refetch()
          void messages.refetch()
        }}
      />
    )
  }
  return (
    <section aria-label={session.data.title} className="min-w-0 space-y-4">
      <h2 className="text-base font-medium break-words">{session.data.title}</h2>
      <div className="space-y-3">
        {list.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing has been asked yet.</p>
        )}
        {list.map((message) => (
          <MessageCard
            key={message.id}
            message={message}
            supervisorAlive={supervisorAlive}
            disabled={blocked !== null}
            onStop={(reason) => cancel.mutate({ messageId: message.id, reason }, { onError })}
          />
        ))}
        <div ref={end} />
      </div>
      <Composer
        projectId={projectId}
        session={session.data}
        busy={busy || send.isPending}
        blocked={blocked}
        onSend={(content) => send.mutate(content, { onError })}
        onError={onError}
      />
    </section>
  )
}
