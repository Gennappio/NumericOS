import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ConnectionStatus } from "./ConnectionStatus"

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: 0 } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe("ConnectionStatus", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("shows connected with the version reported by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "ok",
            app: "numericos",
            version: "0.0.1",
            time_utc: "2026-10-09T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    )

    renderWithQuery(<ConnectionStatus />)
    const status = screen.getByRole("status", { name: "Backend connection" })

    await expect.poll(() => status.getAttribute("data-state")).toBe("connected")
    expect(status).toHaveTextContent("Connected · API v0.0.1")
  })

  it("shows unreachable when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))

    renderWithQuery(<ConnectionStatus />)
    const status = screen.getByRole("status", { name: "Backend connection" })

    await expect.poll(() => status.getAttribute("data-state")).toBe("unreachable")
    expect(status).toHaveTextContent("Backend unreachable")
  })
})
