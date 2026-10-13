import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Annotation, DocumentOut } from "@/api/client"
import type { PipelineCanvasProps } from "@/components/pipeline/PipelineCanvas"
import { annotationRecord, capabilitiesRecord, pipelineRecord } from "@/test/agent"
import { renderProjectView, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { PipelineView } from "./PipelineView"

// The board places and moves its boxes with a library that needs a real layout engine; here
// the boxes are put one after the other. What a box shows, and everything about commenting
// it, is the page's own and is what these tests are about. The board itself is exercised in
// a real browser (e2e/pipeline.spec.ts).
vi.mock("@/components/pipeline/PipelineCanvas", () => ({
  PipelineCanvas: ({ nodes, renderBox }: PipelineCanvasProps) => (
    <div role="application" aria-label="Pipeline board">
      {nodes.map((node) => (
        <div key={node.id}>{renderBox(node.id)}</div>
      ))}
    </div>
  ),
}))

afterEach(() => vi.unstubAllGlobals())

const TEXT = pipelineRecord().markdown

/** Offsets as the API counts them: code points, so the emoji of the title counts once. */
function passage(quote: string): Pick<Annotation, "quote" | "start_offset" | "end_offset"> {
  const start = [...TEXT.slice(0, TEXT.indexOf(quote))].length
  return { quote, start_offset: start, end_offset: start + [...quote].length }
}

function open(document: DocumentOut | null, annotations: Annotation[] = []) {
  const fetchMock = stubApi({
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects/prj_1/pipeline": { document },
    "/v1/annotations": {
      annotations,
      target_version: 1,
      pending_message_id: null,
      pending_session_id: null,
    },
    "/v1/messages/msg_pending": { id: "msg_pending", status: "queued", activity: [] },
  })
  renderProjectView("pipeline", <PipelineView />, "/projects/prj_1/pipeline", {
    project: projectRecord(),
  })
  return fetchMock
}

function posted(fetchMock: ReturnType<typeof stubApi>, path: string): unknown {
  const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
  const call = calls.find(([url, init]) => String(url).endsWith(path) && init?.method === "POST")
  return call ? JSON.parse(String(call[1]!.body)) : undefined
}

function selectIn(root: HTMLElement, from: string, to = from) {
  const find = (wanted: string): [Node, number] => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const at = node.textContent!.indexOf(wanted)
      if (at >= 0) return [node, at]
    }
    throw new Error(`not on the page: ${wanted}`)
  }
  const [first, start] = find(from)
  const [last, end] = find(to)
  const range = document.createRange()
  range.setStart(first, start)
  range.setEnd(last, end + to.length)
  const selection = window.getSelection()!
  selection.removeAllRanges()
  selection.addRange(range)
  fireEvent.mouseUp(root)
}

describe("PipelineView", () => {
  it("offers to ask the agent when nothing was drawn yet", async () => {
    const fetchMock = open(null)

    expect(await screen.findByRole("heading", { name: "The pipeline of this project" })).toBeVisible()
    expect(screen.getByText(/nothing is\s+run and no file is changed/)).toBeVisible()
    expect(screen.queryByRole("application")).toBeNull()
    expect(screen.queryByRole("button", { name: "Download as HTML" })).toBeNull() // nothing to share
    fireEvent.change(screen.getByLabelText(/Instructions for the agent/), {
      target: { value: "Scrivi in italiano." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Draw the pipeline" }))

    await waitFor(() =>
      expect(posted(fetchMock, "/v1/projects/prj_1/pipeline:generate")).toEqual({
        instructions: "Scrivi in italiano.",
      }),
    )
  })

  it("shows the agent at work while the pipeline is drawn for the first time", async () => {
    open(
      pipelineRecord({
        version: 0,
        status: "generating",
        markdown: "",
        pipeline: null,
        message_id: null,
        pending_message_id: "msg_pending",
      }),
    )

    expect(await screen.findByRole("region", { name: "Drawing the pipeline" })).toBeVisible()
    expect(screen.queryByRole("button", { name: "Draw the pipeline" })).toBeNull()
    expect(screen.queryByRole("application")).toBeNull()
  })

  it("says why when the agent's answer was no pipeline", async () => {
    open(
      pipelineRecord({
        version: 0,
        status: "failed",
        status_reason: "the agent's answer had no box that could be used",
        markdown: "",
        pipeline: null,
        message_id: null,
      }),
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The last request did not produce a pipeline: the agent's answer had no box that could be used",
    )
    expect(screen.getByRole("button", { name: "Draw the pipeline" })).toBeEnabled()
  })

  it("draws a box per part of the program, with the summary above and the arrows", async () => {
    open(pipelineRecord())

    const board = await screen.findByRole("application", { name: "Pipeline board" })
    expect(within(board).getAllByRole("article").map((box) => box.getAttribute("aria-label"))).toEqual([
      "Read the parameters",
      "Advance in time",
      "Write the results",
    ])
    expect(
      screen.getByRole("heading", { level: 1, name: "Pipeline of the 2D heat solver 😀" }),
    ).toBeVisible()
    expect(screen.getByText(/One run reads its parameters, advances the scheme/)).toBeVisible()
    const loop = within(board).getByRole("article", { name: "Advance in time" })
    expect(within(loop).getByText(/from its four neighbours/)).toBeVisible()
    expect(within(loop).getByText("first order in time")).toBeVisible()
    // The arrows are also said in words, for whoever does not see the drawing.
    const arrows = screen.getByRole("list", { name: "Arrows of the pipeline" })
    expect(within(arrows).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Read the parametersAdvance in time· n, alpha, dt",
      "Advance in timeWrite the results",
    ])
    expect(screen.getByText("The arrows as a list (2)")).toBeInTheDocument()
    // What it is, who wrote it, where its work is, and the way to ask for it again.
    expect(screen.getByText(/Version 1 · written by claude-sonnet-5-5/)).toBeVisible()
    expect(screen.getByRole("link", { name: "the agent's work" })).toHaveAttribute(
      "href",
      "/projects/prj_1/conversations/ases_pipeline",
    )
    expect(screen.getByText("Written from 2 files of the project")).toBeVisible()
    expect(screen.getByRole("button", { name: "Draw the pipeline again" })).toBeInTheDocument()
    expect(screen.queryByRole("alert")).toBeNull()
    // The board can be handed over as a file.
    expect(screen.getByRole("button", { name: "Download as HTML" })).toBeEnabled()
    // Nothing was commented: the list is folded away, and the board has the room.
    expect(screen.queryByRole("complementary", { name: "Comments" })).toBeNull()
    expect(screen.getByRole("button", { name: /Comments 0/ })).toHaveAttribute("aria-expanded", "false")
  })

  it("marks the boxes whose code changed since, and says which files", async () => {
    open(pipelineRecord({ stale: true, changed_sources: ["heat2d.py"] }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("A file this was written from has changed since.")
    expect(alert).toHaveTextContent("heat2d.py")
    expect(alert).toHaveTextContent("the boxes of the files that changed are marked")
    const loop = screen.getByRole("article", { name: "Advance in time" })
    expect(loop).toHaveAttribute("data-changed", "true")
    expect(within(loop).getByRole("status")).toBeVisible()
    expect(screen.getByRole("article", { name: "Read the parameters" })).toHaveAttribute(
      "data-changed",
      "false",
    )
    expect(screen.getByRole("article", { name: "Write the results" })).toHaveAttribute(
      "data-changed",
      "false",
    )
  })

  it("turns a selection inside a box into a comment on that passage of the pipeline's text", async () => {
    const fetchMock = open(pipelineRecord())
    const board = await screen.findByRole("application", { name: "Pipeline board" })
    const text = board.closest<HTMLElement>("[data-commentable]")!

    selectIn(text, "four neighbours")
    const bar = screen.getByRole("dialog", { name: "Comment on the selected passage" })
    fireEvent.click(within(bar).getByRole("button", { name: "Ask to clarify" }))
    fireEvent.change(within(bar).getByRole("textbox"), { target: { value: "Which stencil?" } })
    fireEvent.click(within(bar).getByRole("button", { name: "Ask to clarify" }))

    await waitFor(() => expect(posted(fetchMock, "/v1/annotations")).toBeDefined())
    // The offsets count from the start of the whole text, in code points.
    expect(posted(fetchMock, "/v1/annotations")).toEqual({
      target_type: "document",
      target_id: "doc_p",
      kind: "clarification",
      body: "Which stencil?",
      ...passage("four neighbours"),
    })
  })

  it("comments the title of a box and the summary as text of the pipeline too", async () => {
    const fetchMock = open(pipelineRecord())
    const board = await screen.findByRole("application", { name: "Pipeline board" })
    const text = board.closest<HTMLElement>("[data-commentable]")!

    selectIn(text, "advances the scheme")
    const bar = screen.getByRole("dialog", { name: "Comment on the selected passage" })
    fireEvent.click(within(bar).getByRole("button", { name: "Add a note" }))
    fireEvent.click(within(bar).getByRole("button", { name: "Add a note" }))
    await waitFor(() => expect(posted(fetchMock, "/v1/annotations")).toBeDefined())
    expect(posted(fetchMock, "/v1/annotations")).toMatchObject({
      kind: "note",
      ...passage("advances the scheme"),
    })

    selectIn(text, "Write the results")
    expect(
      within(screen.getByRole("dialog", { name: "Comment on the selected passage" })).getByRole("button", {
        name: "Request a change",
      }),
    ).toBeVisible()
  })

  it("does not take a selection that runs from one box into another", async () => {
    open(pipelineRecord())
    const board = await screen.findByRole("application", { name: "Pipeline board" })
    const text = board.closest<HTMLElement>("[data-commentable]")!

    selectIn(text, "first order in time", "The final field")

    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("lists the comments of the whole board and shows a clarification inside its box", async () => {
    open(pipelineRecord(), [
      annotationRecord({
        id: "ann_q",
        target_id: "doc_p",
        ...passage("four neighbours"),
        status: "answered",
        body: "Which stencil?",
        response_markdown: "The five-point stencil of the Laplacian.",
      }),
      annotationRecord({
        id: "ann_c",
        target_id: "doc_p",
        kind: "change",
        ...passage("Write the results"),
        body: "Call it output.",
      }),
    ])

    // With comments the list is open, with the two buttons that send them together.
    const comments = await screen.findByRole("complementary", { name: "Comments" })
    expect(comments).toHaveAttribute("data-layout", "panel")
    expect(within(comments).getByRole("article", { name: "Clarification: four neighbours" })).toBeVisible()
    expect(within(comments).getByRole("article", { name: "Change request: Write the results" })).toBeVisible()
    expect(within(comments).getByRole("button", { name: "Clarify (0)" })).toBeDisabled()
    expect(within(comments).getByRole("button", { name: "Resolve (1)…" })).toBeEnabled()

    // The clarification is in the box of its passage, and in no other.
    const loop = screen.getByRole("article", { name: "Advance in time" })
    const inline = within(loop).getByRole("complementary", { name: "Clarification of: four neighbours" })
    expect(within(inline).getByText("The five-point stencil of the Laplacian.")).toBeVisible()
    expect(
      within(screen.getByRole("article", { name: "Write the results" })).queryByRole("complementary"),
    ).toBeNull()

    // The list can be folded away to give the board the room.
    const toggle = screen.getByRole("button", { name: /Comments 2/ })
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(toggle)
    expect(screen.queryByRole("complementary", { name: "Comments" })).toBeNull()
    expect(screen.getByRole("button", { name: /Comments 2.*1 to send/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    )
  })

  it("opens the list of comments on request, with how to comment", async () => {
    open(pipelineRecord())
    fireEvent.click(await screen.findByRole("button", { name: /Comments 0/ }))

    const comments = screen.getByRole("complementary", { name: "Comments" })
    expect(within(comments).getByText(/Select any passage of the text/)).toBeVisible()
  })
})
