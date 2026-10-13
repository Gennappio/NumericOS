import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test, type Locator, type Page } from "@playwright/test"
import { selectPassage, trustedExampleProject, type ProjectRecord } from "./helpers"

/**
 * The pipeline of a project in the browser, end to end: the agent (the stand-in of the test
 * servers) describes the program as boxes and arrows, the page draws them as a board, and
 * the text of any box is commented, clarified and changed as in the other pages.
 */

const SOLVER = "examples/heat2d-python/heat2d.py"

async function drawPipeline(page: Page, project: ProjectRecord): Promise<Locator> {
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("navigation", { name: "Project views" }).getByText("Pipeline").click()
  await expect(page.getByRole("heading", { name: "The pipeline of this project" })).toBeVisible()
  await page.getByRole("button", { name: "Draw the pipeline" }).click()
  const board = page.getByRole("application", { name: "Pipeline board" })
  await expect(board.getByRole("article")).toHaveCount(4)
  return board
}

/** Where a box is on the screen, by its left edge and its top. */
async function placeOf(board: Locator, title: string): Promise<{ x: number; y: number }> {
  const box = await board.getByRole("article", { name: title }).boundingBox()
  expect(box).not.toBeNull()
  return { x: Math.round(box!.x), y: Math.round(box!.y) }
}

test("the program is drawn as boxes and arrows, and the boxes of changed code are marked", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const board = await drawPipeline(page, project)

  // The tab is the view; the title and the summary of the pipeline are above the board.
  const views = page.getByRole("navigation", { name: "Project views" })
  await expect(views.getByText("Pipeline")).toHaveAttribute("aria-current", "page")
  await expect(
    page.getByRole("heading", { level: 1, name: "Pipeline of the 2D heat solver" }),
  ).toBeVisible()
  await expect(page.getByText(/One run reads its parameters, builds the grid/)).toBeVisible()

  // Every part of the program is a box with its kind, its description and its files.
  const loop = board.getByRole("article", { name: "Advance in time" })
  await expect(loop).toHaveAttribute("data-kind", "process")
  await expect(loop.getByRole("heading", { name: "Advance in time" })).toBeVisible()
  await expect(loop).toContainText("The explicit scheme updates every interior point")
  await expect(loop.locator(".katex-display")).toBeVisible()
  await expect(loop.getByText("every time step, until the final time")).toBeVisible()
  await expect(loop.getByRole("list", { name: "Files of Advance in time" })).toHaveText("heat2d.py")
  const parameters = board.getByRole("article", { name: "Read the parameters" })
  await expect(parameters).toHaveAttribute("data-kind", "input")
  await expect(parameters.getByText("Input", { exact: true })).toBeVisible()
  await expect(board.getByRole("article", { name: "Write the results" })).toHaveAttribute(
    "data-kind",
    "output",
  )

  // The arrows say what passes; the one to a box that is not there was left out.
  await expect(board.locator(".react-flow__edge")).toHaveCount(3)
  await expect(board.getByText("initial field")).toBeVisible()
  await page.getByText("The arrows as a list (3)").click()
  await expect(page.getByRole("list", { name: "Arrows of the pipeline" }).getByRole("listitem")).toHaveText([
    /Read the parameters.*Build the grid.*n, alpha, dt/,
    /Build the grid.*Advance in time.*initial field/,
    /Advance in time.*Write the results.*final field/,
  ])

  // Nobody placed the boxes: they go from left to right in the order of a run.
  const places = []
  for (const title of ["Read the parameters", "Build the grid", "Advance in time"]) {
    places.push(await placeOf(board, title))
  }
  expect(places[0].x).toBeLessThan(places[1].x)
  expect(places[1].x).toBeLessThan(places[2].x)
  await expect(parameters).toBeInViewport()
  await page.screenshot({ path: "test-results/screens/pipeline.png", fullPage: true })

  // It says which files it was written from, and persists across a reload.
  await page.getByText("Written from 2 files of the project").click()
  await expect(page.getByRole("list", { name: "Files the pipeline was written from" })).toContainText(
    SOLVER,
  )
  await page.reload()
  await expect(board.getByRole("article")).toHaveCount(4)
  await expect(page.getByRole("alert")).toHaveCount(0)

  // The code changes: the page says so, and marks the boxes that describe the changed file.
  writeFileSync(join(project.root_path!, SOLVER), "print('implicit now')\n")
  await page.reload()
  await expect(page.getByRole("alert")).toContainText(
    "A file this was written from has changed since.",
  )
  await expect(page.getByRole("alert")).toContainText(SOLVER)
  await expect(board.locator('article[data-changed="true"]')).toHaveCount(2)
  await expect(loop).toHaveAttribute("data-changed", "true")
  await expect(loop.getByRole("status")).toHaveText(
    "The code of this part changed since this was written.",
  )
  await expect(parameters).toHaveAttribute("data-changed", "false")
  await page.screenshot({ path: "test-results/screens/pipeline-stale.png", fullPage: true })

  // Drawn again from the code as it is now, nothing is marked any more.
  await page.getByRole("button", { name: "Draw the pipeline again" }).click()
  await expect(page.getByText(/Version 2/)).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await expect(board.locator('article[data-changed="true"]')).toHaveCount(0)
})

test("a passage of a box is commented, clarified inside its box and changed by Resolve", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const board = await drawPipeline(page, project)
  const text = page.locator("[data-commentable]")
  const loop = board.getByRole("article", { name: "Advance in time" })
  await expect(loop).toContainText("four neighbours")
  // Without comments the list is folded away and the board has the whole width.
  await expect(page.getByRole("complementary", { name: "Comments" })).toHaveCount(0)

  // A passage of a box is selected: the same bar as in every other text of the agent.
  await selectPassage(text, "four neighbours")
  const bar = page.getByRole("dialog", { name: "Comment on the selected passage" })
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  await bar.getByRole("textbox").fill("Which stencil is this?")
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  const comments = page.getByRole("complementary", { name: "Comments" })
  const question = comments.getByRole("article", { name: "Clarification: four neighbours" })
  await expect(question).toContainText("Which stencil is this?")
  /** The passages highlighted on the page under a name, as the browser holds them. */
  const highlighted = (name: string) =>
    page.evaluate(
      (key) => [...(CSS.highlights.get(key) ?? [])].map((range) => range.toString()),
      name,
    )
  expect(await highlighted("nos-focus")).toEqual(["four neighbours"]) // the new comment

  // Clarify answers inside the box of the passage; the pipeline itself is not redrawn.
  await comments.getByRole("button", { name: "Clarify (1)" }).click()
  await expect(question).toHaveAttribute("data-status", "answered")
  const inline = loop.getByRole("complementary", { name: "Clarification of: four neighbours" })
  await expect(inline).toContainText("the bound comes from")
  await expect(page.getByText(/Version 1/)).toBeVisible()
  await page.screenshot({ path: "test-results/screens/pipeline-clarified.png", fullPage: true })

  // A selection that runs from one box into another is about no single part: no bar.
  await page.keyboard.press("Escape")
  await text.evaluate((root) => {
    const words = (box: string) =>
      document
        .createTreeWalker(root.querySelector(`article[data-node="${box}"] p`)!, NodeFilter.SHOW_TEXT)
        .nextNode()!
    const range = document.createRange()
    range.setStart(words("grid"), 2)
    range.setEnd(words("time-loop"), 12)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    root.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }))
  })
  await expect(bar).toHaveCount(0)

  // The title of a box is text of the pipeline too: a change is requested on it.
  await selectPassage(text, "Advance in time")
  await bar.getByRole("button", { name: "Request a change" }).click()
  await bar.getByRole("textbox").fill("Call it time stepping.")
  await bar.getByRole("button", { name: "Request a change" }).click()
  const change = comments.getByRole("article", { name: "Change request: Advance in time" })
  await expect(change).toHaveAttribute("data-status", "open")

  await comments.getByRole("button", { name: "Resolve (1)…" }).click()
  const dialog = page.getByRole("dialog", { name: "Resolve 1 change request" })
  await dialog
    .getByLabel(/Instructions for the agent/)
    .fill("REPLACE Advance in time=>Step in time")
  await dialog.getByRole("button", { name: "Resolve" }).click()

  // The agent gave the pipeline again as boxes and arrows: the board is drawn from them.
  const renamed = board.getByRole("article", { name: "Step in time" })
  await expect(renamed).toContainText("The explicit scheme updates every interior point")
  await expect(board.getByRole("article", { name: "Advance in time" })).toHaveCount(0)
  await expect(board.getByRole("article")).toHaveCount(4)
  await expect(page.getByText(/Version 2/)).toBeVisible()
  await expect(change).toHaveAttribute("data-status", "resolved")
  await expect(change).toContainText("passage no longer in the text")
  // The clarification is still on its passage, in the box as it is now.
  await expect(question).toHaveAttribute("data-anchor", "attached")
  await expect(
    renamed.getByRole("complementary", { name: "Clarification of: four neighbours" }),
  ).toBeVisible()
  await page.screenshot({ path: "test-results/screens/pipeline-resolved.png", fullPage: true })

  // The board puts its boxes on the page in its own time: after a reload the passages are
  // highlighted all the same, in the boxes as they are drawn.
  await page.reload()
  await expect(board.getByRole("article")).toHaveCount(4)
  await expect.poll(() => highlighted("nos-settled")).toEqual(["four neighbours"])

  // From the list to the board: the passage of a comment is brought into view.
  await board.getByRole("article", { name: "Read the parameters" }).scrollIntoViewIfNeeded()
  await question.getByRole("button", { name: "four neighbours" }).click()
  await expect(renamed).toBeInViewport()
})

test("boxes are moved by their bar, stay where they were put, and are tidied up on request", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const board = await drawPipeline(page, project)
  /** Where a box is from its neighbour: the board itself may be shown from another point. */
  const fromNeighbour = async () => {
    const box = await placeOf(board, "Build the grid")
    const neighbour = await placeOf(board, "Read the parameters")
    return { x: box.x - neighbour.x, y: box.y - neighbour.y }
  }
  /** The same place, give or take the rounding of a board shown from another point. */
  const at = (place: { x: number; y: number }) => async () => {
    const now = await fromNeighbour()
    return Math.abs(now.x - place.x) <= 2 && Math.abs(now.y - place.y) <= 2
  }
  const before = await fromNeighbour()
  const neighbour = await placeOf(board, "Read the parameters")

  // The coloured bar of a box is its handle.
  const handle = board.getByRole("article", { name: "Build the grid" }).locator("header")
  const grip = await handle.boundingBox()
  const from = { x: Math.round(grip!.x + 40), y: Math.round(grip!.y + grip!.height / 2) }
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x + 60, from.y + 180, { steps: 12 })
  await page.mouse.up()
  const moved = await fromNeighbour()
  expect(moved.x - before.x).toBeGreaterThan(40)
  expect(moved.y - before.y).toBeGreaterThan(150)
  expect(await placeOf(board, "Read the parameters")).toEqual(neighbour) // only that box moved

  // A press on the text of a box selects text: the box stays where it is. (Whole pixels, as
  // a mouse gives them: Chromium does not always extend a selection that was started at a
  // fractional position on scaled content.)
  const words = board.getByRole("article", { name: "Build the grid" }).getByText("A uniform grid")
  const line = await words.evaluate((element) => {
    const range = document.createRange()
    range.selectNodeContents(element)
    const first = range.getClientRects()[0]
    return { x: Math.ceil(first.x), y: Math.round(first.y + first.height / 2) }
  })
  await page.mouse.move(line.x + 2, line.y)
  await page.mouse.down()
  await page.mouse.move(line.x + 90, line.y, { steps: 9 })
  await page.mouse.up()
  expect(await at(moved)()).toBe(true)
  expect(await page.evaluate(() => window.getSelection()!.toString())).toMatch(/^A? ?uniform/)
  await expect(page.getByRole("dialog", { name: "Comment on the selected passage" })).toBeVisible()
  await page.screenshot({ path: "test-results/screens/pipeline-moved.png", fullPage: true })

  // This browser remembers where the boxes were put.
  await page.reload()
  await expect(board.getByRole("article")).toHaveCount(4)
  await expect.poll(at(moved)).toBe(true)

  // Tidy up puts every box back in the order of a run, and forgets where they were put.
  await page.getByRole("button", { name: "Tidy up" }).click()
  await expect.poll(at(before)).toBe(true)
  await page.reload()
  await expect(board.getByRole("article")).toHaveCount(4)
  await expect.poll(at(before)).toBe(true)
})
