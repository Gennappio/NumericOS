import { screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { HEALTH_OK, renderApp, stubApi, stubUnreachableApi } from "@/test/render"
import { ConnectionStatus } from "./ConnectionStatus"

describe("ConnectionStatus", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("shows connected with the version reported by the API", async () => {
    stubApi({ "/v1/health": HEALTH_OK })

    renderApp(<ConnectionStatus />)
    const status = screen.getByRole("status", { name: "Backend connection" })

    await expect.poll(() => status.getAttribute("data-state")).toBe("connected")
    expect(status).toHaveTextContent("Connected · API v0.0.1")
  })

  it("says so when the database still needs a migration", async () => {
    stubApi({ "/v1/health": { ...HEALTH_OK, status: "degraded", schema_revision: null } })

    renderApp(<ConnectionStatus />)
    const status = screen.getByRole("status", { name: "Backend connection" })

    await expect.poll(() => status.textContent).toContain("database needs migration")
  })

  it("shows unreachable when the API is down", async () => {
    stubUnreachableApi()

    renderApp(<ConnectionStatus />)
    const status = screen.getByRole("status", { name: "Backend connection" })

    await expect.poll(() => status.getAttribute("data-state")).toBe("unreachable")
    expect(status).toHaveTextContent("Backend unreachable")
  })
})
