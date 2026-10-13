import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { AgentPolicy } from "@/api/client"
import { capabilitiesRecord, policyRecord } from "@/test/agent"
import { stubApi } from "@/test/render"
import { PolicyPanel } from "./PolicyPanel"

afterEach(() => vi.unstubAllGlobals())

const EVERY_TASK: AgentPolicy["available"] = [
  "conversation",
  "clarify",
  "resolve",
  "theory",
  "file_description",
  "pipeline",
  "plan",
]

function open(policy: AgentPolicy = policyRecord(), onError = vi.fn()) {
  const fetchMock = stubApi({ "/v1/projects/prj_1/agent-policy": { ...policy, version: 2 } })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PolicyPanel
        projectId="prj_1"
        policy={policy}
        capabilities={capabilitiesRecord()}
        disabled={false}
        onError={onError}
      />
    </QueryClientProvider>,
  )
  return fetchMock
}

function saved(fetchMock: ReturnType<typeof stubApi>): Record<string, unknown> | undefined {
  const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
  const put = calls.find(([, init]) => init?.method === "PUT")
  return put ? (JSON.parse(String(put[1]!.body)) as Record<string, unknown>) : undefined
}

const firstOption = (label: string) =>
  within(screen.getByLabelText(label)).getAllByRole("option")[0].textContent

describe("PolicyPanel", () => {
  it("lists a default and every task with the provider's models and efforts", () => {
    open()

    const table = screen.getByRole("table", { name: "Models and effort per task" })
    expect(within(table).getAllByRole("row")).toHaveLength(9) // header, default, 7 tasks
    expect(screen.getByLabelText("Model for Conversation")).toHaveValue("claude-sonnet-5-5")
    expect(screen.getByLabelText("Effort for Conversation")).toHaveValue("medium")
    expect(screen.getByLabelText("Model for Conversation")).toBeEnabled()
    // A task whose feature is not built is shown and cannot be set.
    expect(screen.getByLabelText("Model for Clarify")).toBeDisabled()
    expect(screen.getByLabelText("Effort for Theory page")).toBeDisabled()
    expect(screen.getAllByText(/Not available yet/)).toHaveLength(6)
    expect(
      within(screen.getByLabelText("Model for Conversation")).getByRole("option", {
        name: /Haiku 5.5 — lightest/,
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled() // nothing changed
  })

  it("says which coding agent is at work and what leaving the choice to it means", () => {
    open()

    expect(screen.getByTestId("coding-agent")).toHaveTextContent(
      "Coding agent: Claude Code 2.1.296 /usr/local/bin/claude",
    )
    expect(screen.getByTestId("coding-agent")).toHaveTextContent(
      "The only coding agent NumericOS drives today",
    )
    // Nothing is chosen as the default: the choice is the agent's, and it was never seen.
    expect(screen.getByLabelText("Default model")).toHaveValue("")
    expect(screen.getByLabelText("Default effort")).toHaveValue("")
    expect(firstOption("Default model")).toBe("Claude Code's own setting")
    expect(firstOption("Default effort")).toBe("Claude Code's own setting")
    const explained = screen.getByTestId("policy-explained")
    expect(explained).toHaveTextContent(
      "Claude Code's own setting leaves the choice to Claude Code: the model and the effort it uses when you start it yourself in a terminal.",
    )
    expect(explained).toHaveTextContent("NumericOS neither reads nor changes that setting.")
    expect(explained).toHaveTextContent("No turn ran on it yet")
    // A row that does not choose says what it follows.
    expect(firstOption("Model for Clarify")).toBe("Default (Claude Code's own setting)")
    expect(firstOption("Effort for Clarify")).toBe("Default (Claude Code's own setting)")
  })

  it("says what the agent's own setting was last seen to be", () => {
    open(
      policyRecord({
        provider_default: {
          model: "claude-fable-5-1",
          seen_at: "2026-10-12T21:27:00Z",
          in_project: true,
        },
      }),
    )

    expect(firstOption("Default model")).toBe("Claude Code's own setting (last seen: Fable 5.1)")
    expect(screen.getByTestId("policy-explained")).toHaveTextContent(
      /The last turn that ran on it here was answered by Fable 5.1 \(claude-fable-5-1, .*2026.*\)\. The effort it uses is not reported\./,
    )
  })

  it("says when the agent's own setting was only seen in another project, by its name as given", () => {
    open(
      policyRecord({
        provider_default: { model: "claude-opus-5-5", seen_at: "2026-10-12T21:27:00Z", in_project: false },
      }),
    )

    // Not one of the models offered here: shown as the provider named it.
    expect(firstOption("Default model")).toBe("Claude Code's own setting (last seen: claude-opus-5-5)")
    expect(screen.getByTestId("policy-explained")).toHaveTextContent(
      "The last turn that ran on it, in another project, was answered by claude-opus-5-5",
    )
  })

  it("shows on every row that follows the default what the default is, as it is being set", () => {
    open(policyRecord({ available: EVERY_TASK }))

    fireEvent.change(screen.getByLabelText("Default model"), { target: { value: "claude-haiku-5-5" } })
    fireEvent.change(screen.getByLabelText("Default effort"), { target: { value: "low" } })

    expect(firstOption("Model for Theory page")).toBe("Default (Haiku 5.5)")
    expect(firstOption("Effort for Theory page")).toBe("Default (low)")
    // A row that chose keeps its choice: the default is for the ones that do not.
    expect(screen.getByLabelText("Model for Conversation")).toHaveValue("claude-sonnet-5-5")
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled()
  })

  it("saves the default and the changed choices with the policy version", async () => {
    const fetchMock = open()

    fireEvent.change(screen.getByLabelText("Default model"), { target: { value: "claude-sonnet-5-5" } })
    fireEvent.change(screen.getByLabelText("Model for Conversation"), {
      target: { value: "claude-haiku-5-5" },
    })
    fireEvent.change(screen.getByLabelText("Effort for Conversation"), { target: { value: "" } })
    const save = screen.getByRole("button", { name: "Save" })
    expect(save).toBeEnabled()
    fireEvent.click(save)

    await vi.waitFor(() => expect(saved(fetchMock)).toBeDefined())
    const body = saved(fetchMock) as { version: number; defaults: unknown; tasks: Record<string, unknown> }
    expect(body.version).toBe(1)
    expect(body.defaults).toEqual({ model: "claude-sonnet-5-5", effort: null })
    expect(body.tasks.conversation).toEqual({ model: "claude-haiku-5-5", effort: null })
    expect(body.tasks.file_description).toEqual({ model: "claude-haiku-5-5", effort: "low" })
  })

  it("puts every task back on the default in one click", async () => {
    const fetchMock = open(policyRecord({ available: EVERY_TASK }))
    const follow = screen.getByRole("button", { name: "Leave every task on Default" })

    fireEvent.change(screen.getByLabelText("Default effort"), { target: { value: "low" } })
    fireEvent.click(follow)

    expect(screen.getByLabelText("Model for Conversation")).toHaveValue("")
    expect(screen.getByLabelText("Effort for File descriptions")).toHaveValue("")
    expect(follow).toBeDisabled() // no task chooses any more
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await vi.waitFor(() => expect(saved(fetchMock)).toBeDefined())
    const body = saved(fetchMock) as { defaults: unknown; tasks: Record<string, unknown> }
    expect(body.defaults).toEqual({ model: null, effort: "low" })
    expect(Object.values(body.tasks)).toEqual(Array(7).fill({ model: null, effort: null }))
  })
})
