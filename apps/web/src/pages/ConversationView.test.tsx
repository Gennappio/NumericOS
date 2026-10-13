import { screen } from "@testing-library/react"
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
import { ConversationView } from "./ConversationView"

afterEach(() => vi.unstubAllGlobals())

function open(project: Project, extra: Record<string, unknown> = {}, sessionId = "ases_1") {
  stubApi({
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects/prj_1/agent-policy": policyRecord(),
    "/v1/agent-sessions/ases_1": sessionRecord(),
    "/v1/agent-sessions/ases_1/messages": { messages: [userMessage(), answerRecord()] },
    ...extra,
  })
  return renderProjectView(
    "conversations/:sessionId",
    <ConversationView />,
    `/projects/prj_1/conversations/${sessionId}`,
    { project },
  )
}

describe("ConversationView", () => {
  it("shows the conversation with its messages and the composer", async () => {
    open(projectRecord())

    expect(await screen.findByRole("article", { name: "Agent answer" })).toBeVisible()
    expect(screen.getByRole("article", { name: "Your message" })).toBeVisible()
    expect(
      screen.getByRole("heading", { name: "Why is the explicit scheme unstable?" }),
    ).toBeVisible()
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled()
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled() // nothing typed yet
    expect(screen.getByLabelText("Permission mode")).toHaveValue("edit")
    // The next turn runs with the policy's choice for conversations unless overridden here.
    expect(screen.getByLabelText("Model")).toHaveValue("")
    expect(screen.getByRole("option", { name: "Policy: Sonnet 5.5" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Policy: medium" })).toBeInTheDocument()
    // Everything is in order: no precondition panel. The policy table is in the Agent view.
    expect(screen.queryByText("Before the agent can work")).toBeNull()
    expect(screen.queryByRole("table", { name: "Models and effort per task" })).toBeNull()
  })

  it("shows what a conversation that does not choose takes from the project's default", async () => {
    const none = { model: null, effort: null }
    open(projectRecord(), {
      "/v1/projects/prj_1/agent-policy": policyRecord({
        defaults: { model: "claude-haiku-5-5", effort: null },
        tasks: { ...policyRecord().tasks, conversation: none },
      }),
    })

    await screen.findByRole("article", { name: "Agent answer" })
    // The model comes from the default; no effort is chosen anywhere: the agent's own.
    expect(await screen.findByRole("option", { name: "Policy: Haiku 5.5" })).toBeInTheDocument()
    expect(
      screen.getByRole("option", { name: "Policy: Claude Code's own setting" }),
    ).toBeInTheDocument()
  })

  it("invites to ask in a conversation where nothing was asked yet", async () => {
    open(projectRecord(), {
      "/v1/agent-sessions/ases_1": sessionRecord({ title: "New conversation", message_count: 0 }),
      "/v1/agent-sessions/ases_1/messages": { messages: [] },
    })

    expect(await screen.findByRole("heading", { name: "New conversation" })).toBeVisible()
    expect(screen.getByText(/Nothing has been asked yet/)).toBeVisible()
    expect(screen.getByLabelText("Message to the agent")).toBeEnabled()
  })

  it("blocks the composer and explains while the directory is not trusted", async () => {
    open(projectRecord({ execution_trusted_at: null }))

    expect(await screen.findByText("Before the agent can work")).toBeVisible()
    expect(screen.getByText("Not allowed yet.", { exact: false })).toBeVisible()
    expect(screen.getByRole("button", { name: "Allow execution in this directory…" })).toBeEnabled()
    expect(await screen.findByLabelText("Message to the agent")).toBeDisabled()
    expect(screen.getByText("Execution in the project directory is not allowed yet.")).toBeVisible()
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

  it("reports a conversation that does not exist", async () => {
    open(projectRecord(), {}, "ases_gone")

    expect(await screen.findByText("Could not load the conversation")).toBeVisible()
    expect(screen.queryByLabelText("Message to the agent")).toBeNull()
  })
})
