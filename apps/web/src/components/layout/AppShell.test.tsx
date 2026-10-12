import { fireEvent, screen, within } from "@testing-library/react"
import { Route, Routes, useParams } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { capabilitiesRecord, sessionRecord } from "@/test/agent"
import { HEALTH_OK, renderApp, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { AppShell } from "./AppShell"

afterEach(() => vi.unstubAllGlobals())

const HEAT = projectRecord()
const WAVE = projectRecord({ id: "prj_2", name: "Wave 1D" })

/** What the page under the sidebar would show: enough to tell where a link led. */
function Where() {
  const { sessionId } = useParams()
  return <p>conversation {sessionId}</p>
}

function open(route: string, extra: Record<string, unknown> = {}) {
  const fetchMock = stubApi({
    "/v1/health": HEALTH_OK,
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects": { projects: [HEAT, WAVE] },
    "/v1/projects/prj_1/agent-sessions": {
      sessions: [
        sessionRecord({ id: "ases_2", title: "What does the solver assume?", message_count: 4 }),
        sessionRecord(),
      ],
    },
    "/v1/projects/prj_2/agent-sessions": { sessions: [] },
    ...extra,
  })
  renderApp(
    <AppShell>
      <Routes>
        <Route path="/projects/:projectId/conversations/:sessionId" element={<Where />} />
        <Route path="*" element={<p>another page</p>} />
      </Routes>
    </AppShell>,
    route,
  )
  return fetchMock
}

describe("AppShell", () => {
  it("lists the conversations of every project under the project's name", async () => {
    open("/projects/prj_1/conversations/ases_1")

    const sidebar = screen.getByRole("navigation", { name: "Projects" })
    const conversations = await within(sidebar).findByRole("list", {
      name: "Conversations of Heat 2D",
    })
    const links = within(conversations).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual([
      "What does the solver assume?",
      "Why is the explicit scheme unstable?",
    ])
    expect(links[0]).toHaveAttribute("href", "/projects/prj_1/conversations/ases_2")
    // The conversation on screen is marked, and so is the project it belongs to.
    expect(links[1]).toHaveAttribute("aria-current", "page")
    expect(links[0]).not.toHaveAttribute("aria-current")
    expect(within(sidebar).getByRole("link", { name: "Heat 2D" })).toHaveAttribute(
      "aria-current",
      "page",
    )
    expect(links[1]).toHaveAttribute("title", expect.stringContaining("Edit files · 2 messages"))
    // A project without conversations has no list; only the one on screen says so.
    expect(within(sidebar).getByRole("link", { name: "Wave 1D" })).toBeVisible()
    expect(within(sidebar).queryByRole("list", { name: "Conversations of Wave 1D" })).toBeNull()
    expect(within(sidebar).queryByText(/No conversation yet/)).toBeNull()
  })

  it("starts a conversation from the project's row and opens it", async () => {
    const fetchMock = open("/projects/prj_2", {
      "POST /v1/projects/prj_2/agent-sessions": sessionRecord({
        id: "ases_new",
        project_id: "prj_2",
        title: "New conversation",
        message_count: 0,
      }),
    })

    expect(await screen.findByText("No conversation yet: start one with +.")).toBeVisible()
    const start = screen.getByRole("button", { name: "New conversation in Wave 1D" })
    await vi.waitFor(() => expect(start).toBeEnabled())
    fireEvent.click(start)

    expect(await screen.findByText("conversation ases_new")).toBeVisible()
    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
    const post = calls.find(([, init]) => init?.method === "POST")
    expect(String(post?.[0])).toMatch(/\/v1\/projects\/prj_2\/agent-sessions$/)
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ permission_mode: "edit" })
  })

  it("opens the conversation in which nothing was asked yet instead of a second empty one", async () => {
    const fetchMock = open("/projects/prj_1", {
      "/v1/projects/prj_1/agent-sessions": {
        sessions: [
          sessionRecord({ id: "ases_empty", title: "New conversation", message_count: 0 }),
          sessionRecord(),
        ],
      },
    })

    await screen.findByRole("link", { name: "New conversation" })
    fireEvent.click(screen.getByRole("button", { name: "New conversation in Heat 2D" }))

    expect(await screen.findByText("conversation ases_empty")).toBeVisible()
    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
    expect(calls.some(([, init]) => init?.method === "POST")).toBe(false)
  })

  it("says why no conversation can be started while the directory is not trusted", async () => {
    open("/projects/prj_1", {
      "/v1/projects": { projects: [projectRecord({ execution_trusted_at: null }), WAVE] },
    })

    const start = await screen.findByRole("button", { name: "New conversation in Heat 2D" })
    expect(start).toBeDisabled()
    expect(start).toHaveAttribute("title", "Execution in the project directory is not allowed yet.")
    await vi.waitFor(() =>
      expect(screen.getByRole("button", { name: "New conversation in Wave 1D" })).toBeEnabled(),
    )
  })

  it("shows the newest conversations first and the rest on request", async () => {
    const sessions = Array.from({ length: 7 }, (_, index) =>
      sessionRecord({ id: `ases_${index}`, title: `Question ${index}` }),
    )
    open("/projects/prj_1", { "/v1/projects/prj_1/agent-sessions": { sessions } })

    const conversations = await screen.findByRole("list", { name: "Conversations of Heat 2D" })
    expect(within(conversations).getAllByRole("link")).toHaveLength(5)
    fireEvent.click(within(conversations).getByRole("button", { name: "Show all 7" }))
    expect(within(conversations).getAllByRole("link")).toHaveLength(7)
    fireEvent.click(within(conversations).getByRole("button", { name: "Show fewer" }))
    expect(within(conversations).getAllByRole("link")).toHaveLength(5)
  })

  it("never hides the conversation on screen among the older ones", async () => {
    const sessions = Array.from({ length: 7 }, (_, index) =>
      sessionRecord({ id: `ases_${index}`, title: `Question ${index}` }),
    )
    open("/projects/prj_1/conversations/ases_6", {
      "/v1/projects/prj_1/agent-sessions": { sessions },
    })

    const conversations = await screen.findByRole("list", { name: "Conversations of Heat 2D" })
    expect(within(conversations).getAllByRole("link")).toHaveLength(7)
    expect(within(conversations).getByRole("link", { name: "Question 6" })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })
})
