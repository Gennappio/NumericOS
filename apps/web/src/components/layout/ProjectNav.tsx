import { MessageSquareIcon, PlusIcon } from "lucide-react"
import { useState } from "react"
import { NavLink, useNavigate } from "react-router"
import type { AgentSession, Project } from "@/api/client"
import { useAgentSessions, useCreateAgentSession } from "@/api/queries"
import { useAgentReadiness } from "@/components/agent/readiness"
import { Badge } from "@/components/ui/badge"
import { PERMISSION_MODE_LABELS } from "@/lib/agent"
import { describeError } from "@/lib/errors"
import { formatTimestamp } from "@/lib/time"
import { cn } from "@/lib/utils"

/** Conversations listed under a project before the rest is asked for. */
export const SHOWN_CONVERSATIONS = 5

const PROJECT_DOTS = [
  "bg-indigo-500",
  "bg-fuchsia-500",
  "bg-cyan-500",
  "bg-amber-500",
  "bg-violet-500",
  "bg-sky-500",
  "bg-pink-500",
  "bg-teal-500",
]

/** The same colour for the same project every time, to tell projects apart at a glance. */
function projectDot(id: string): string {
  let sum = 0
  for (const character of id) sum = (sum * 31 + character.charCodeAt(0)) % 9973
  return PROJECT_DOTS[sum % PROJECT_DOTS.length]
}

interface ProjectNavProps {
  project: Project
  /** The page of this project is the one on screen. */
  open: boolean
  /** The conversation on screen, if one is. */
  conversationId: string | undefined
  offline: boolean
}

/**
 * A project in the sidebar: the link to its page, and under it its conversations with the
 * coding agent, newest first. A project has one page; its conversations open inside it.
 */
export function ProjectNav({ project, open, conversationId, offline }: ProjectNavProps) {
  const navigate = useNavigate()
  const sessions = useAgentSessions(project.id, open)
  const { blocked } = useAgentReadiness(project, offline)
  const create = useCreateAgentSession(project.id)
  const [all, setAll] = useState(false)
  const list = sessions.data?.sessions ?? []
  // The conversation on screen is never among the hidden ones.
  const beyond = list.findIndex((session) => session.id === conversationId) >= SHOWN_CONVERSATIONS
  const shown = all || beyond ? list : list.slice(0, SHOWN_CONVERSATIONS)
  const address = (session: AgentSession) => `/projects/${project.id}/conversations/${session.id}`

  function start() {
    // A conversation in which nothing was asked yet is the new one: no second empty one.
    const empty = list.find((session) => session.message_count === 0)
    if (empty) {
      navigate(address(empty))
      return
    }
    create.mutate({ permission_mode: "edit" }, { onSuccess: (session) => navigate(address(session)) })
  }

  return (
    <li>
      <div className="flex items-center gap-1">
        <NavLink
          to={`/projects/${project.id}`}
          className={({ isActive }) =>
            cn(
              "flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md px-3 py-2 text-sm",
              isActive
                ? "bg-indigo-50 font-medium text-indigo-950"
                : "text-muted-foreground hover:bg-muted/60",
            )
          }
        >
          <span className="flex min-w-0 items-center gap-2">
            <span
              aria-hidden="true"
              className={cn("inline-block size-2.5 shrink-0 rounded-full", projectDot(project.id))}
            />
            <span className="break-words">{project.name}</span>
          </span>
          {project.is_demo && <Badge variant="outline">Demo</Badge>}
        </NavLink>
        <button
          type="button"
          aria-label={`New conversation in ${project.name}`}
          title={blocked ?? "New conversation with the agent"}
          disabled={blocked !== null || create.isPending}
          onClick={start}
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-fuchsia-700 hover:bg-fuchsia-50 disabled:text-muted-foreground disabled:opacity-50 disabled:hover:bg-transparent"
        >
          <PlusIcon aria-hidden="true" className="size-4" />
        </button>
      </div>

      {create.isError && (
        <p role="alert" className="px-3 py-1 text-xs break-words text-red-800">
          {describeError(create.error)}
        </p>
      )}
      {sessions.isError && (
        <p role="alert" className="px-3 py-1 text-xs break-words text-red-800">
          Could not load the conversations: {describeError(sessions.error)}
        </p>
      )}
      {open && sessions.data && list.length === 0 && (
        <p className="py-1 pr-2 pl-7 text-xs text-muted-foreground">
          No conversation yet: start one with +.
        </p>
      )}
      {list.length > 0 && (
        <ul
          aria-label={`Conversations of ${project.name}`}
          className="mt-0.5 ml-4 space-y-0.5 border-l border-border pl-1.5"
        >
          {shown.map((session) => (
            <li key={session.id}>
              <NavLink
                to={address(session)}
                title={`${session.title}\n${PERMISSION_MODE_LABELS[session.permission_mode]} · ${
                  session.message_count === 1 ? "1 message" : `${session.message_count} messages`
                } · ${formatTimestamp(session.updated_at)}`}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-md px-2 py-1 text-[0.8125rem]",
                    isActive
                      ? "bg-fuchsia-50 font-medium text-fuchsia-950"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )
                }
              >
                <MessageSquareIcon aria-hidden="true" className="size-3.5 shrink-0 text-fuchsia-500" />
                <span className="truncate">{session.title}</span>
              </NavLink>
            </li>
          ))}
          {list.length > SHOWN_CONVERSATIONS && !beyond && (
            <li>
              <button
                type="button"
                onClick={() => setAll(!all)}
                className="rounded-md px-2 py-1 text-xs text-muted-foreground underline-offset-4 hover:underline"
              >
                {all ? "Show fewer" : `Show all ${list.length}`}
              </button>
            </li>
          )}
        </ul>
      )}
    </li>
  )
}
