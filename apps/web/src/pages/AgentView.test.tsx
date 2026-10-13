import { screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Project } from "@/api/client"
import { capabilitiesRecord, policyRecord } from "@/test/agent"
import { renderProjectView, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { AgentView } from "./AgentView"

afterEach(() => vi.unstubAllGlobals())

const READY = {
  "/v1/agents/capabilities": capabilitiesRecord(),
  "/v1/workers": { workers: [], alive: 1 },
}

function open(project: Project, routes: Record<string, unknown> = {}) {
  stubApi({ ...READY, "/v1/projects/prj_1/agent-policy": policyRecord(), ...routes })
  return renderProjectView("agent", <AgentView />, "/projects/prj_1/agent", { project })
}

describe("AgentView", () => {
  it("shows the models and effort per task, and nothing else", async () => {
    open(projectRecord())

    // The table is on the page as it opens, not folded away.
    const table = await screen.findByRole("table", { name: "Models and effort per task" })
    expect(table).toBeVisible()
    expect(within(table).getAllByRole("row")).toHaveLength(9) // the header, the default, 7 tasks
    expect(screen.getByLabelText("Default model")).toHaveValue("")
    expect(screen.getByTestId("coding-agent")).toHaveTextContent("Coding agent: Claude Code")
    expect(screen.getByLabelText("Model for Conversation")).toHaveValue("claude-sonnet-5-5")
    expect(screen.getByLabelText("Effort for File descriptions")).toHaveValue("low")
    expect(screen.getByRole("heading", { name: "Models and effort per task" })).toBeVisible()
    // The conversations are in the sidebar, under the project's name: none of them here.
    expect(screen.queryByRole("navigation", { name: "Conversations" })).toBeNull()
    expect(screen.queryByLabelText("Message to the agent")).toBeNull()
    expect(screen.queryByRole("button", { name: "New conversation" })).toBeNull()
    // Everything is in order: no precondition panel.
    expect(screen.queryByText("Before the agent can work")).toBeNull()
  })

  it("says what stands in the agent's way while the directory is not trusted", async () => {
    open(projectRecord({ execution_trusted_at: null }))

    expect(await screen.findByText("Before the agent can work")).toBeVisible()
    expect(screen.getByRole("button", { name: "Allow execution in this directory…" })).toBeEnabled()
    // The policy can be set before the agent may work.
    expect(await screen.findByRole("table", { name: "Models and effort per task" })).toBeVisible()
  })

  it("reports a policy that could not be loaded", async () => {
    stubApi(READY) // the policy is not among the answers: the API says 404
    renderProjectView("agent", <AgentView />, "/projects/prj_1/agent", { project: projectRecord() })

    expect(await screen.findByText("Could not load the policy")).toBeVisible()
  })
})
