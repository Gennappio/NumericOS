import { screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Project } from "@/api/client"
import {
  answerRecord,
  capabilitiesRecord,
  policyRecord,
  sessionRecord,
  userMessage,
} from "@/test/agent"
import { renderProjectView, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { AgentView } from "./AgentView"

afterEach(() => vi.unstubAllGlobals())

function open(project: Project, extra: Record<string, unknown> = {}) {
  stubApi({
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects/prj_1/agent-policy": policyRecord(),
    "/v1/projects/prj_1/agent-sessions": { sessions: [sessionRecord()] },
    "/v1/agent-sessions/ases_1": sessionRecord(),
    "/v1/agent-sessions/ases_1/messages": { messages: [userMessage(), answerRecord()] },
    ...extra,
  })
  return renderProjectView("agent/:sessionId?", <AgentView />, "/projects/prj_1/agent", {
    project,
  })
}

describe("AgentView", () => {
  it("shows the newest conversation with its messages and the composer", async () => {
    open(projectRecord())

    expect(await screen.findByRole("article", { name: "Agent answer" })).toBeVisible()
    expect(screen.getByRole("article", { name: "Your message" })).toBeVisible()
    const conversations = screen.getByRole("navigation", { name: "Conversations" })
    expect(
      within(conversations).getByRole("link", { name: /Why is the explicit scheme unstable/ }),
    ).toHaveAttribute("aria-current", "page")
    expect(within(conversations).getByText("Edit files")).toBeVisible() // its mode, as a tag
    expect(within(conversations).getByText(/2 messages/)).toBeVisible()
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled()
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled() // nothing typed yet
    expect(screen.getByLabelText("Permission mode")).toHaveValue("edit")
    // The next turn runs with the policy's choice for conversations unless overridden here.
    expect(screen.getByLabelText("Model")).toHaveValue("")
    expect(screen.getByRole("option", { name: "Policy: Sonnet 5.5" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Policy: medium" })).toBeInTheDocument()
    // Everything is in order: no precondition panel.
    expect(screen.queryByText("Before the agent can work")).toBeNull()
  })

  it("blocks the composer and explains while the directory is not trusted", async () => {
    open(projectRecord({ execution_trusted_at: null }))

    expect(await screen.findByText("Before the agent can work")).toBeVisible()
    expect(screen.getByText("Not allowed yet.", { exact: false })).toBeVisible()
    expect(screen.getByRole("button", { name: "Allow execution in this directory…" })).toBeEnabled()
    expect(await screen.findByLabelText("Message to the agent")).toBeDisabled()
    expect(screen.getByText(/not allowed yet \(see above\)/)).toBeVisible()
  })

  it("says when the agent command is not installed", async () => {
    open(projectRecord(), {
      "/v1/agents/capabilities": capabilitiesRecord({
        available: false,
        path: null,
        version: null,
        problem: "'claude' was not found on the PATH of the NumericOS processes.",
      }),
    })

    expect(await screen.findByText("Not available.")).toBeVisible()
    expect(screen.getAllByText(/'claude' was not found/).length).toBeGreaterThan(0)
    expect(await screen.findByLabelText("Message to the agent")).toBeDisabled()
  })

  it("invites to start when there is no conversation", async () => {
    open(projectRecord(), { "/v1/projects/prj_1/agent-sessions": { sessions: [] } })

    expect(await screen.findByText("No conversation yet.")).toBeVisible()
    expect(screen.getByText(/Start a conversation to ask the agent/)).toBeVisible()
    expect(screen.getByRole("button", { name: "New conversation" })).toBeEnabled()
  })
})
