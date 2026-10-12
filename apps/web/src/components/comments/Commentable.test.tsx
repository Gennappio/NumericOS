import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Annotation } from "@/api/client"
import { annotationRecord } from "@/test/agent"
import { renderApp, stubApi } from "@/test/render"
import { Commentable } from "./Commentable"

afterEach(() => vi.unstubAllGlobals())

const SOURCE = [
  "# Heat 😀 2D",
  "",
  "The scheme is **stable** when $r \\le 1/2$.",
  "",
  "It uses central differences in space.",
  "",
  "## Limits",
  "",
  "Only periodic boundaries.",
].join("\n")

/** Offsets as the API counts them: code points, so the emoji of the title counts once. */
function passage(quote: string): Pick<Annotation, "quote" | "start_offset" | "end_offset"> {
  const start = [...SOURCE.slice(0, SOURCE.indexOf(quote))].length
  return { quote, start_offset: start, end_offset: start + [...quote].length }
}

function open(annotations: Annotation[], extra: Record<string, unknown> = {}, version = 1) {
  const fetchMock = stubApi({
    "/v1/annotations": {
      annotations,
      target_version: 1,
      pending_message_id: null,
      pending_session_id: null,
    },
    ...extra,
  })
  renderApp(
    <Commentable
      projectId="prj_1"
      target={{ type: "document", id: "doc_1" }}
      source={SOURCE}
      version={version}
      label="Heat 2D"
      layout="side"
      blocked={null}
      supervisorAlive
      onError={() => {}}
    />,
  )
  return fetchMock
}

function posted(fetchMock: ReturnType<typeof stubApi>, path: string): unknown {
  const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
  const call = calls.find(([url, init]) => String(url).endsWith(path) && init?.method === "POST")
  return call ? JSON.parse(String(call[1]!.body)) : undefined
}

function selectIn(root: HTMLElement, wanted: string) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const at = node.textContent!.indexOf(wanted)
    if (at < 0) continue
    const range = document.createRange()
    range.setStart(node, at)
    range.setEnd(node, at + wanted.length)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    fireEvent.mouseUp(root)
    return
  }
  throw new Error(`not on the page: ${wanted}`)
}

describe("Commentable", () => {
  it("invites to select a passage when nothing was commented yet", async () => {
    open([])

    const comments = await screen.findByRole("complementary", { name: "Comments" })
    expect(within(comments).getByText(/Select any passage of the text/)).toBeVisible()
    expect(within(comments).getByRole("button", { name: "Clarify (0)" })).toBeDisabled()
    expect(within(comments).getByRole("button", { name: "Resolve (0)…" })).toBeDisabled()
  })

  it("turns a selection into a comment on that exact passage of the source", async () => {
    const fetchMock = open([])
    const text = screen.getByRole("article", { name: "Heat 2D" })
    await screen.findByText(/Select any passage/)

    selectIn(text, "central differences")
    const bar = screen.getByRole("dialog", { name: "Comment on the selected passage" })
    fireEvent.click(within(bar).getByRole("button", { name: "Request a change" }))
    expect(within(bar).getByText("central differences")).toBeVisible() // what is being commented
    const save = within(bar).getByRole("button", { name: "Request a change" })
    expect(save).toBeDisabled() // a request must say what it asks
    fireEvent.change(within(bar).getByRole("textbox"), { target: { value: "Use a 9-point stencil." } })
    fireEvent.click(save)

    await waitFor(() => expect(posted(fetchMock, "/v1/annotations")).toBeDefined())
    expect(posted(fetchMock, "/v1/annotations")).toEqual({
      target_type: "document",
      target_id: "doc_1",
      kind: "change",
      body: "Use a 9-point stencil.",
      ...passage("central differences"),
    })
  })

  it("comments a formula as a whole, by its source", async () => {
    const fetchMock = open([])
    const text = screen.getByRole("article", { name: "Heat 2D" })
    await screen.findByText(/Select any passage/)

    const formula = text.querySelector(".katex-html")!
    const range = document.createRange()
    range.selectNodeContents(formula)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    fireEvent.mouseUp(text)
    const bar = screen.getByRole("dialog", { name: "Comment on the selected passage" })
    fireEvent.click(within(bar).getByRole("button", { name: "Add a note" }))
    fireEvent.click(within(bar).getByRole("button", { name: "Add a note" }))

    await waitFor(() => expect(posted(fetchMock, "/v1/annotations")).toBeDefined())
    expect(posted(fetchMock, "/v1/annotations")).toMatchObject({
      kind: "note",
      body: "",
      quote: "$r \\le 1/2$",
    })
  })

  it("lists the comments with what the agent answered, and counts what can be sent", async () => {
    open([
      annotationRecord({
        id: "ann_q",
        ...passage("stable"),
        status: "answered",
        body: "Why only then?",
        response_markdown: "Because $|1-4r| \\le 1$.",
      }),
      annotationRecord({ id: "ann_c", kind: "change", body: "Go implicit.", ...passage("central differences") }),
      annotationRecord({
        id: "ann_d",
        kind: "change",
        status: "declined",
        body: "Rewrite in Fortran.",
        response_markdown: "A different project.",
        ...passage("periodic boundaries"),
      }),
      annotationRecord({
        id: "ann_lost",
        kind: "note",
        body: "old",
        quote: "a sentence that is gone",
        anchor_state: "detached",
      }),
      annotationRecord({ id: "ann_w", kind: "note", status: "dismissed", ...passage("Limits") }),
    ])

    const comments = await screen.findByRole("complementary", { name: "Comments" })
    await within(comments).findByRole("heading", { name: "Comments 4" }) // the withdrawn one is not listed
    expect(within(comments).getByRole("button", { name: "Clarify (0)" })).toBeDisabled()
    expect(within(comments).getByRole("button", { name: "Resolve (1)…" })).toBeEnabled()
    const declined = within(comments).getByRole("article", { name: "Change request: periodic boundaries" })
    expect(within(declined).getByText("Declined by the agent")).toBeVisible()
    expect(within(declined).getByText("Why the agent declined")).toBeVisible()
    const lost = within(comments).getByRole("article", { name: "Note: a sentence that is gone" })
    expect(within(lost).getByText(/passage no longer in the text/)).toBeVisible()
    expect(within(lost).getByRole("button", { name: "a sentence that is gone" })).toBeDisabled()
  })

  it("shows a clarification right after the paragraph of its passage", async () => {
    open([
      annotationRecord({
        id: "ann_q",
        ...passage("stable"),
        status: "answered",
        body: "Why only then?",
        response_markdown: "Because $|1-4r| \\le 1$.",
      }),
    ])
    const text = screen.getByRole("article", { name: "Heat 2D" })

    const inline = await within(text).findByRole("complementary", { name: "Clarification of: stable" })
    expect(within(inline).getByText(/Why only then\?/)).toBeVisible()
    expect(inline.querySelector(".katex")).not.toBeNull()
    const blocks = [...text.querySelector(".markdown")!.children].map((node) =>
      node.hasAttribute("data-slot") ? "CLARIFICATION" : node.textContent!.slice(0, 12),
    )
    expect(blocks.slice(1, 4)).toEqual(["The scheme i", "CLARIFICATION", "It uses cent"])
  })

  it("does not place comments of another version of the text", async () => {
    open(
      [
        annotationRecord({
          ...passage("stable"),
          status: "answered",
          response_markdown: "Because.",
        }),
      ],
      {},
      2,
    )

    const comments = await screen.findByRole("complementary", { name: "Comments" })
    const card = await within(comments).findByRole("article", { name: "Clarification: stable" })
    expect(within(card).getByText(/passage no longer in the text/)).toBeVisible()
    expect(screen.queryByRole("complementary", { name: /Clarification of/ })).toBeNull()
  })

  it("asks before Resolve, saying that files will be edited, and sends the mode chosen", async () => {
    const fetchMock = open(
      [annotationRecord({ id: "ann_c", kind: "change", body: "Go implicit.", ...passage("central differences") })],
      { "/v1/annotations:resolve": { queued: 1, message_id: "msg_r", session_id: "ases_r" } },
    )
    const comments = await screen.findByRole("complementary", { name: "Comments" })

    fireEvent.click(await within(comments).findByRole("button", { name: "Resolve (1)…" }))
    const dialog = screen.getByRole("dialog", { name: "Resolve 1 change request" })
    expect(within(dialog).getByText(/edits the files\s+of the project directly/)).toBeVisible()
    fireEvent.change(within(dialog).getByLabelText("What the agent may do"), { target: { value: "full" } })
    fireEvent.click(within(dialog).getByRole("button", { name: "Resolve" }))

    await waitFor(() => expect(posted(fetchMock, "/v1/annotations:resolve")).toBeDefined())
    expect(posted(fetchMock, "/v1/annotations:resolve")).toEqual({
      target_type: "document",
      target_id: "doc_1",
      permission_mode: "full",
    })
  })

  it("sends every open clarification with one click", async () => {
    const fetchMock = open(
      [annotationRecord({ ...passage("stable") }), annotationRecord({ id: "ann_2", ...passage("Limits") })],
      { "/v1/annotations:clarify": { queued: 2, message_id: "msg_c", session_id: "ases_c" } },
    )
    const comments = await screen.findByRole("complementary", { name: "Comments" })

    fireEvent.click(await within(comments).findByRole("button", { name: "Clarify (2)" }))

    await waitFor(() => expect(posted(fetchMock, "/v1/annotations:clarify")).toBeDefined())
    expect(posted(fetchMock, "/v1/annotations:clarify")).toEqual({
      target_type: "document",
      target_id: "doc_1",
    })
  })
})
