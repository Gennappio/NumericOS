import { screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { HEALTH_OK, renderApp, stubApi, stubUnreachableApi } from "@/test/render"
import { ProjectsPage } from "./ProjectsPage"

const DEMO_PROJECT = {
  id: "prj_01J9W2Z4K7QX8YB3N5M6T0R1S2",
  name: "Demo: 2D heat equation stability",
  research_question: "Which time steps keep the solver stable?",
  description: "",
  root_path: null,
  is_demo: true,
  version: 1,
  created_at: "2026-10-10T08:00:00Z",
  updated_at: "2026-10-10T08:00:00Z",
}

describe("ProjectsPage", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("explains the empty state instead of showing placeholder projects", async () => {
    stubApi({ "/v1/health": HEALTH_OK, "/v1/projects": { projects: [] } })

    renderApp(<ProjectsPage />)

    expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "New project" })).toBeEnabled()
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument()
  })

  it("lists projects from the API and labels demo data", async () => {
    stubApi({ "/v1/health": HEALTH_OK, "/v1/projects": { projects: [DEMO_PROJECT] } })

    renderApp(<ProjectsPage />)

    const link = await screen.findByRole("link", { name: /Demo: 2D heat equation stability/ })
    expect(link).toHaveAttribute("href", `/projects/${DEMO_PROJECT.id}`)
    expect(link).toHaveTextContent("Demo data")
    expect(link).toHaveTextContent("Which time steps keep the solver stable?")
  })

  it("reports a load failure and blocks changes when the backend is unreachable", async () => {
    stubUnreachableApi()

    renderApp(<ProjectsPage />)

    expect(await screen.findByText("Could not load projects")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled()
    await expect
      .poll(() => screen.getByRole("button", { name: "New project" }).hasAttribute("disabled"))
      .toBe(true)
  })
})
