import { fireEvent, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { capabilitiesRecord, documentRecord, fileRecord } from "@/test/agent"
import { renderProjectView, stubApi } from "@/test/render"
import { projectRecord } from "@/test/runs"
import { FilesView } from "./FilesView"

afterEach(() => vi.unstubAllGlobals())

const FILES = {
  root: "/work/heat2d",
  truncated: false,
  counts: { total: 4, described: 1, stale: 1, generating: 1, failed: 0, undescribed: 1 },
  files: [
    fileRecord(),
    fileRecord({
      path: "src/kernel.f90",
      description: { ...fileRecord().description!, stale: true, summary: "The stencil." },
    }),
    fileRecord({
      path: "results/u_final.csv",
      category: "output",
      description: {
        ...fileRecord().description!,
        status: "generating",
        pending: true,
        summary: "",
      },
    }),
    fileRecord({ path: "fig/grid.png", category: "image", viewable_image: true, description: null }),
  ],
}

function open(extra: Record<string, unknown> = {}, project = projectRecord()) {
  const fetchMock = stubApi({
    "/v1/agents/capabilities": capabilitiesRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    "/v1/projects/prj_1/files": FILES,
    "/v1/projects/prj_1/files/description": documentRecord({
      kind: "file_description",
      key: "src/heat2d.py",
      markdown: "Solves $u_t = \\alpha \\nabla^2 u$ with forward Euler.",
    }),
    ...extra,
  })
  renderProjectView("files", <FilesView />, "/projects/prj_1/files", { project })
  return fetchMock
}

describe("FilesView", () => {
  it("lists the files by directory with what is known about each", async () => {
    open()

    expect(await screen.findByTestId("file-counts")).toHaveTextContent(
      "4 files · 1 described · 1 changed since · 1 being described · 1 not described",
    )
    const source = screen.getByRole("region", { name: "src" })
    expect(within(source).getAllByRole("listitem")).toHaveLength(2)
    expect(within(source).getByText("The explicit solver of the heat equation.")).toBeVisible()
    expect(within(source).getByText("Changed since")).toBeVisible()
    expect(within(screen.getByRole("region", { name: "results" })).getByText("Being described")).toBeVisible()
    expect(within(screen.getByRole("region", { name: "fig" })).getByText("Not described")).toBeVisible()
    expect(screen.getByRole("button", { name: "Describe the 1 not described" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Update the 1 changed" })).toBeEnabled()
  })

  it("opens a file to its whole description, and an image to the image", async () => {
    const { container } = { container: document.body }
    open()

    const row = (await screen.findByText("heat2d.py")).closest("li")!
    fireEvent.click(within(row).getByRole("button", { expanded: false }))
    expect(await within(row).findByText(/with forward Euler/)).toBeVisible()
    expect(container.querySelector(".katex")).not.toBeNull()
    expect(within(row).getByRole("button", { name: "Describe it again" })).toBeEnabled()

    const image = screen.getByText("grid.png").closest("li")!
    fireEvent.click(within(image).getByRole("button", { expanded: false }))
    expect(within(image).getByRole("img", { name: "fig/grid.png" })).toHaveAttribute(
      "src",
      "http://127.0.0.1:8765/v1/projects/prj_1/files/content?path=fig%2Fgrid.png",
    )
    expect(within(image).getByRole("button", { name: "Describe this file" })).toBeEnabled()
    // Opening another file closes the first: one description is read at a time.
    expect(within(row).queryByText(/with forward Euler/)).toBeNull()
  })

  it("filters by path and by kind", async () => {
    open()
    await screen.findByTestId("file-counts")

    fireEvent.change(screen.getByLabelText("Filter by path"), { target: { value: "kernel" } })
    expect(screen.getByText("1 of 4 shown")).toBeVisible()
    expect(screen.queryByText("heat2d.py")).toBeNull()

    fireEvent.change(screen.getByLabelText("Filter by path"), { target: { value: "" } })
    fireEvent.change(screen.getByLabelText("Filter by kind"), { target: { value: "output" } })
    expect(screen.getByText("u_final.csv")).toBeVisible()
    expect(screen.queryByText("kernel.f90")).toBeNull()
  })

  it("asks the agent for the files in a state, with the instructions given", async () => {
    const fetchMock = open({
      "/v1/projects/prj_1/files:describe": { queued: 1, turns: 1, skipped: 0, left: 0, message_ids: ["m"] },
    })
    await screen.findByTestId("file-counts")

    fireEvent.change(screen.getByLabelText("Instructions for the agent"), {
      target: { value: "Scrivi in italiano." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Update the 1 changed" }))

    expect(await screen.findByText("Asked the agent to describe 1 file in 1 turn.")).toBeVisible()
    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL, RequestInit?][]
    const post = calls.find(([, init]) => init?.method === "POST")!
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      scope: "stale",
      instructions: "Scrivi in italiano.",
    })
  })

  it("does not read the directory of a project that was not trusted", async () => {
    open({}, projectRecord({ execution_trusted_at: null }))

    expect(await screen.findByText(/The files are listed once/)).toBeVisible()
    expect(screen.getByText("Before the agent can work")).toBeVisible()
    expect(screen.queryByTestId("file-counts")).toBeNull()
  })
})
