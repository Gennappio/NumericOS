import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { capabilitiesRecord, policyRecord } from "@/test/agent"
import { stubApi } from "@/test/render"
import { PolicyPanel } from "./PolicyPanel"

afterEach(() => vi.unstubAllGlobals())

function open(onError = vi.fn()) {
  const fetchMock = stubApi({ "/v1/projects/prj_1/agent-policy": policyRecord({ version: 2 }) })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PolicyPanel
        projectId="prj_1"
        policy={policyRecord()}
        capabilities={capabilitiesRecord()}
        disabled={false}
        onError={onError}
      />
    </QueryClientProvider>,
  )
  return fetchMock
}

describe("PolicyPanel", () => {
  it("lists every task with the provider's models and efforts, editable only where built", () => {
    open()

    const table = screen.getByRole("table", { name: "Models and effort per task" })
    expect(within(table).getAllByRole("row")).toHaveLength(8) // header + 7 tasks
    expect(screen.getByLabelText("Model for Conversation")).toHaveValue("claude-sonnet-5-5")
    expect(screen.getByLabelText("Effort for Conversation")).toHaveValue("medium")
    expect(screen.getByLabelText("Model for Conversation")).toBeEnabled()
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

  it("saves the changed choices with the policy version", async () => {
    const fetchMock = open()

    fireEvent.change(screen.getByLabelText("Model for Conversation"), {
      target: { value: "claude-haiku-5-5" },
    })
    fireEvent.change(screen.getByLabelText("Effort for Conversation"), { target: { value: "" } })
    const save = screen.getByRole("button", { name: "Save" })
    expect(save).toBeEnabled()
    fireEvent.click(save)

    await vi.waitFor(() => {
      const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
      const put = calls.find(([, init]) => init?.method === "PUT")
      expect(put).toBeDefined()
      const body = JSON.parse(String(put![1]!.body))
      expect(body.version).toBe(1)
      expect(body.tasks.conversation).toEqual({ model: "claude-haiku-5-5", effort: null })
      expect(body.tasks.file_description).toEqual({ model: "claude-haiku-5-5", effort: "low" })
    })
  })
})
