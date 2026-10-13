import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ShareButton } from "./ShareButton"

const download = vi.hoisted(() => vi.fn())
vi.mock("@/lib/export/html", async (original) => ({
  ...(await original<typeof import("@/lib/export/html")>()),
  download,
}))

afterEach(() => download.mockReset())

describe("ShareButton", () => {
  it("makes the file when pressed and hands it to the browser under its name", async () => {
    const build = vi.fn().mockResolvedValue({ name: "heat-2d-pipeline.html", html: "<!doctype html>", imagesLeftOutside: 0 })
    const onNotice = vi.fn()
    render(<ShareButton build={build} onNotice={onNotice} onError={vi.fn()} />)
    const button = screen.getByRole("button", { name: "Download as HTML" })
    expect(build).not.toHaveBeenCalled() // nothing is prepared before it is asked for

    fireEvent.click(button)
    expect(screen.getByRole("button", { name: "Preparing…" })).toBeDisabled()

    await waitFor(() => expect(download).toHaveBeenCalledWith("heat-2d-pipeline.html", "<!doctype html>"))
    expect(await screen.findByRole("button", { name: "Download as HTML" })).toBeEnabled()
    expect(onNotice).not.toHaveBeenCalled()
  })

  it("says so when figures could not be put into the file", async () => {
    const onNotice = vi.fn()
    render(
      <ShareButton
        build={() => Promise.resolve({ name: "t.html", html: "", imagesLeftOutside: 2 })}
        onNotice={onNotice}
        onError={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Download as HTML" }))

    await waitFor(() => expect(onNotice).toHaveBeenCalledOnce())
    expect(onNotice.mock.calls[0][0]).toMatch(/^2 image\(s\) could not be put into the file/)
    expect(download).toHaveBeenCalledOnce() // the file is handed over all the same
  })

  it("reports a failure and is ready to be pressed again", async () => {
    const onError = vi.fn()
    const failure = new Error("no layout")
    render(<ShareButton build={() => Promise.reject(failure)} onNotice={vi.fn()} onError={onError} />)

    fireEvent.click(screen.getByRole("button", { name: "Download as HTML" }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith(failure))
    expect(download).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Download as HTML" })).toBeEnabled()
  })
})
