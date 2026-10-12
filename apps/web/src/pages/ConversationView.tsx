import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router"
import type { AgentCapabilities, AgentPolicy } from "@/api/client"
import {
  isTurnActive,
  useAgentPolicy,
  useAgentSession,
  useCancelMessage,
  useMessages,
  useSendMessage,
} from "@/api/queries"
import { Composer } from "@/components/agent/Composer"
import { MessageCard } from "@/components/agent/MessageCard"
import { AgentPreconditions } from "@/components/agent/Preconditions"
import { useAgentReadiness } from "@/components/agent/readiness"
import { ErrorPanel } from "@/components/ErrorPanel"
import { Notice } from "@/components/Notice"
import { describeError } from "@/lib/errors"
import { useProjectContext } from "@/pages/projectContext"

/**
 * One conversation with the coding agent about this project, opened from the list under the
 * project's name in the sidebar. The agent works in the project's directory as you; the
 * preconditions (the directory trusted, a supervisor alive, the agent command installed) are
 * shown as they are, never assumed.
 */
export function ConversationView() {
  const { project, live, offline } = useProjectContext()
  const { sessionId = "" } = useParams()
  const readiness = useAgentReadiness(project, offline)
  const policy = useAgentPolicy(project.id, live)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="space-y-5">
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      <AgentPreconditions project={project} offline={offline} readiness={readiness} />
      <Conversation
        key={sessionId}
        projectId={project.id}
        sessionId={sessionId}
        policy={policy.data}
        capabilities={readiness.capabilities}
        supervisorAlive={readiness.supervisorAlive}
        blocked={readiness.blocked}
        onError={(error) => setNotice(describeError(error))}
      />
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
    <section aria-label={session.data.title} className="mx-auto max-w-4xl min-w-0 space-y-4">
      <h2 className="text-base font-medium break-words">{session.data.title}</h2>
      <div className="space-y-3">
        {list.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nothing has been asked yet. Ask the agent about this project: what its code does,
            what theory it implements, what a result means.
          </p>
        )}
        {list.map((message) => (
          <MessageCard
            key={message.id}
            message={message}
            supervisorAlive={supervisorAlive}
            blocked={blocked}
            onError={onError}
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
