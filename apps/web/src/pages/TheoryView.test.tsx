import { screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { DocumentOut } from "@/api/client"
import { answerRecord, capabilitiesRecord, documentRecord } from "@/test/agent"
import { renderProjectView, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { TheoryView } from "./TheoryView"

afterEach(() => vi.unstubAllGlobals())

function open(document: DocumentOut | null, extra: Record<string, unknown> = {}) {
  stubApi({
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects/prj_1/theory": { document },
    ...extra,
  })
  return renderProjectView("theory", <TheoryView />, "/projects/prj_1/theory", {
    project: projectRecord(),
  })
}

describe("TheoryView", () => {
  it("offers to write the theory when there is none, saying what the agent will do", async () => {
    open(null)

    expect(await screen.findByRole("heading", { name: "The theory of this project" })).toBeVisible()
    expect(screen.getByText(/It only reads: no file is changed/)).toBeVisible()
    expect(screen.getByRole("button", { name: "Write the theory" })).toBeEnabled()
    expect(screen.getByLabelText(/Instructions for the agent/)).toHaveValue("")
    expect(screen.queryByRole("button", { name: "Download as HTML" })).toBeNull() // nothing to share
  })

  it("renders the theory as a paper with its formulas, figures and sources", async () => {
    const { container } = open(documentRecord())

    const paper = await screen.findByRole("article", {
      name: "Explicit scheme for the 2D heat equation",
    })
    expect(within(paper).getByRole("heading", { level: 1 })).toBeVisible()
    expect(container.querySelector(".paper .katex-display")).not.toBeNull()
    // A path of the project becomes the address of the file in the project directory.
    expect(within(paper).getByRole("img", { name: "The grid" })).toHaveAttribute(
      "src",
      "http://127.0.0.1:8765/v1/projects/prj_1/files/content?path=docs%2Fgrid.png",
    )
    expect(screen.getByText(/Version 1 · written by claude-fable-5-1/)).toBeVisible()
    expect(screen.getByText("Written from 2 files of the project")).toBeVisible()
    expect(screen.getByRole("link", { name: "the agent's work" })).toHaveAttribute(
      "href",
      "/projects/prj_1/conversations/ases_theory",
    )
    expect(screen.queryByRole("alert")).toBeNull()
    // The paper can be handed over as a file.
    expect(screen.getByRole("button", { name: "Download as HTML" })).toBeEnabled()
    // The request to write it again starts from the instructions of the last one.
    expect(screen.getByLabelText(/Instructions for the agent/)).toHaveValue("Scrivi in italiano.")
  })

  it("says which files changed since, and keeps the text readable", async () => {
    open(documentRecord({ stale: true, changed_sources: ["heat2d.py"] }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("A file this was written from has changed since.")
    expect(alert).toHaveTextContent("heat2d.py")
    expect(screen.getByRole("article")).toBeVisible()
    expect(screen.getByText("changed since")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Write the theory again" })).toBeEnabled()
  })

  it("shows the agent at work while the theory is being written", async () => {
    open(
      documentRecord({
        version: 0,
        markdown: "",
        status: "generating",
        message_id: null,
        pending_message_id: "msg_pending",
      }),
      {
        "/v1/messages/msg_pending": answerRecord({
          id: "msg_pending",
          status: "running",
          markdown: "",
          model_requested: "claude-fable-5-1",
        }),
      },
    )

    const progress = await screen.findByRole("region", { name: "Writing the theory" })
    expect(await within(progress).findByText("Working")).toBeVisible()
    expect(within(progress).getByRole("button", { name: "Stop" })).toBeEnabled()
    expect(within(progress).getByText("heat2d.py", { exact: false })).toBeVisible()
    expect(screen.queryByRole("article")).toBeNull()
    expect(screen.queryByRole("button", { name: "Write the theory" })).toBeNull()
  })

  it("says why a request produced nothing", async () => {
    open(
      documentRecord({
        version: 0,
        markdown: "",
        status: "failed",
        message_id: null,
        status_reason: "the agent's turn ended failed: error_max_budget",
      }),
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The last request did not produce a document: the agent's turn ended failed: error_max_budget",
    )
    expect(screen.getByRole("button", { name: "Write the theory" })).toBeEnabled()
  })
})
