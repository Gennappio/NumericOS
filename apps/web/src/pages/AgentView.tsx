import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router"
import type { AgentCapabilities, AgentPolicy, PermissionMode } from "@/api/client"
import {
  isTurnActive,
  useAgentPolicy,
  useAgentSession,
  useAgentSessions,
  useCancelMessage,
  useCreateAgentSession,
  useMessages,
  useSendMessage,
} from "@/api/queries"
import { Composer } from "@/components/agent/Composer"
import { MessageCard } from "@/components/agent/MessageCard"
import { PolicyPanel } from "@/components/agent/PolicyPanel"
import { SessionList } from "@/components/agent/SessionList"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { useAgentReadiness } from "@/components/agent/readiness"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
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
  const readiness = useAgentReadiness(project, offline)
  const { blocked, supervisorAlive, capabilities } = readiness
  const policy = useAgentPolicy(project.id, live)
  const sessions = useAgentSessions(project.id, live)
  const create = useCreateAgentSession(project.id)
  const [notice, setNotice] = useState<string | null>(null)
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

      <AgentPreconditions project={project} offline={offline} readiness={readiness} />

      <details className="group rounded-lg border border-border bg-muted/30">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium">
          Models and effort per task
          <span className="font-normal text-muted-foreground">
            {" "}
            · which model answers each kind of task, and how hard it tries
          </span>
        </summary>
        <div className="p-3 pt-0">
          {policy.data ? (
            <PolicyPanel
              key={policy.data.version}
              projectId={project.id}
              policy={policy.data}
              capabilities={capabilities}
              disabled={offline}
              onError={(error) => setNotice(describeError(error))}
            />
          ) : policy.isError ? (
            <ErrorPanel
              title="Could not load the policy"
              error={policy.error}
              onRetry={() => void policy.refetch()}
            />
          ) : (
            <p role="status" className="text-sm text-muted-foreground">
              Loading…
            </p>
          )}
        </div>
      </details>

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
            policy={policy.data}
            capabilities={capabilities}
            supervisorAlive={supervisorAlive}
            blocked={blocked}
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

interface ConversationProps {
  projectId: string
  sessionId: string
  policy: AgentPolicy | undefined
  capabilities: AgentCapabilities | undefined
  supervisorAlive: boolean
  blocked: string | null
  onError: (error: unknown) => void
}

function Conversation({
  projectId,
  sessionId,
  policy,
  capabilities,
  supervisorAlive,
  blocked,
  onError,
}: ConversationProps) {
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
        policy={policy}
        capabilities={capabilities}
        busy={busy || send.isPending}
        blocked={blocked}
        onSend={(content) => send.mutate(content, { onError })}
        onError={onError}
      />
    </section>
  )
}
