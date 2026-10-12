import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { renderApp, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { ExecutionPanel } from "./ExecutionPanel"

afterEach(() => vi.unstubAllGlobals())

const WORKER = {
  id: "wrk_1",
  pid: 4242,
  hostname: "lab",
  version: "0.0.1",
  max_parallel_runs: 2,
  started_at: "2026-10-12T09:00:00Z",
  heartbeat_at: "2026-10-12T09:00:05Z",
  stopped_at: null,
  alive: true,
  active_runs: 1,
}

describe("ExecutionPanel", () => {
  it("says that nothing can be queued and nothing would start it", async () => {
    stubApi({ "/v1/workers": { workers: [], alive: 0 } })
    renderApp(
      <ExecutionPanel project={projectRecord({ execution_trusted_at: null })} disabled={false} />,
    )

    expect(screen.getByText(/Not allowed yet/)).toBeVisible()
    expect(screen.getByText("/work/heat2d")).toBeVisible()
    expect(await screen.findByText("No supervisor is running.")).toBeVisible()
    expect(screen.getByText("make worker")).toBeVisible()
  })

  it("shows the directory that is trusted and the supervisor that is alive", async () => {
    stubApi({ "/v1/workers": { workers: [WORKER], alive: 1 } })
    renderApp(<ExecutionPanel project={projectRecord()} disabled={false} />)

    expect(screen.getByText(/^Allowed in/)).toBeVisible()
    expect(await screen.findByText(/Running: process 4242 on lab, 1 of 2 runs in progress/)).toBeVisible()
    expect(screen.queryByRole("button", { name: /Allow execution/ })).toBeNull()
  })

  it("asks for an explicit confirmation of the exact directory before allowing execution", async () => {
    const fetchMock = stubApi({ "/v1/workers": { workers: [], alive: 0 } })
    renderApp(
      <ExecutionPanel project={projectRecord({ execution_trusted_at: null })} disabled={false} />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Allow execution in this directory…" }))
    const confirm = await screen.findByRole("button", { name: "Allow execution" })
    expect(confirm).toBeDisabled() // not before the person has said they understand
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(confirm)

    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
    await waitFor(() =>
      expect(calls.some(([input]) => String(input).endsWith(":trust-execution"))).toBe(true),
    )
    const sent = calls.find(([input]) => String(input).endsWith(":trust-execution"))
    expect(String(sent![0])).toMatch(/\/v1\/projects\/prj_1:trust-execution$/)
    expect(JSON.parse(String(sent![1]!.body))).toEqual({
      version: 2,
      root_path: "/work/heat2d", // the directory, not the project name
    })
  })

  it("explains what is missing when the project has no code path", async () => {
    stubApi({ "/v1/workers": { workers: [], alive: 0 } })
    renderApp(<ExecutionPanel project={projectRecord({ root_path: null })} disabled={false} />)

    expect(screen.getByText(/This project has no code path/)).toBeVisible()
    expect(screen.queryByRole("button", { name: /Allow execution/ })).toBeNull()
  })
})
