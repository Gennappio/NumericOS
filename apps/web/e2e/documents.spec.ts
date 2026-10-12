import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test } from "@playwright/test"
import { column, trustedExampleProject } from "./helpers"

/**
 * The documents the agent writes about a project, in the browser, end to end: the theory as a
 * paper, the descriptions of the files, the plan on the board. A real supervisor starts the
 * agent command (the stand-in the test servers are configured with).
 */

const SOLVER = "examples/heat2d-python/heat2d.py"

test("the theory is written as a paper and says when the code it describes has changed", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("navigation", { name: "Project views" }).getByText("Theory").click()

  await expect(page.getByRole("heading", { name: "The theory of this project" })).toBeVisible()
  await page.getByLabel("Instructions for the agent").fill(`READ ${SOLVER}`)
  await page.getByRole("button", { name: "Write the theory" }).click()

  const paper = page.getByRole("article", { name: "Explicit scheme for the 2D heat equation" })
  await expect(paper.getByRole("heading", { level: 1 })).toHaveText(
    "Explicit scheme for the 2D heat equation",
  )
  await expect(paper.locator(".katex-display")).toBeVisible()
  await expect(paper.getByRole("table")).toContainText("update of (1)")
  // A figure of the repository, served from the project directory, with its caption.
  const figure = paper.getByRole("img", { name: "The grid of the solver" })
  await expect(figure).toBeVisible()
  expect(
    await figure.evaluate((img) => (img as unknown as { naturalWidth: number }).naturalWidth),
  ).toBe(16)
  await expect(page.getByText("Version 1 · written by fake-model")).toBeVisible()
  await page.getByText("Written from 1 file of the project").click()
  await expect(
    page.getByRole("list", { name: "Files the theory was written from" }).getByText(SOLVER),
  ).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await page.screenshot({ path: "test-results/screens/theory.png", fullPage: true })

  // The code changes: the page says which file, and offers to write the theory again.
  writeFileSync(join(project.root_path!, SOLVER), "print('an implicit scheme now')\n")
  await page.reload()
  const stale = page.getByRole("alert")
  await expect(stale).toContainText("A file this was written from has changed since.")
  await expect(stale).toContainText(SOLVER)
  await page.screenshot({ path: "test-results/screens/theory-stale.png", fullPage: true })
  await page.getByRole("button", { name: "Write the theory again" }).click()
  await expect(page.getByText("Version 2 · written by fake-model")).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("the files of the project are described, and a changed file is marked and updated", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/files`)

  const counts = page.getByTestId("file-counts")
  await expect(counts).toContainText("0 described")
  const total = Number((await counts.textContent())!.match(/(\d+) files/)![1])
  expect(total).toBeGreaterThan(5)
  await page.getByRole("button", { name: `Describe the ${total} not described` }).click()
  await expect(page.getByRole("status").filter({ hasText: "Asked the agent" })).toContainText(
    `Asked the agent to describe ${total} files`,
  )
  await expect(counts).toContainText(`${total} described`, { timeout: 30_000 })
  await expect(counts).toContainText("0 being described")

  await page.getByLabel("Filter by path").fill("heat2d.py")
  const row = page.locator(`[data-path="${SOLVER}"]`)
  await expect(row).toHaveAttribute("data-state", "described")
  await expect(row).toContainText(`Fake summary of ${SOLVER}.`)
  await row.getByRole("button", { expanded: false }).click()
  await expect(row.locator(".katex")).toBeVisible()
  await expect(row.getByText("Version 1 · written by claude-sonnet-5-5")).toBeVisible()

  // An image is shown where it is described.
  await page.getByLabel("Filter by path").fill("")
  await page.getByLabel("Filter by kind").selectOption("image")
  const image = page.locator('[data-path="docs/grid.png"]')
  await image.getByRole("button", { expanded: false }).click()
  await expect(image.getByRole("img", { name: "docs/grid.png" })).toBeVisible()
  await page.screenshot({ path: "test-results/screens/files.png", fullPage: true })

  // The file changes: its description is marked, and one click asks for it again.
  writeFileSync(join(project.root_path!, SOLVER), "print('edited')\n")
  await page.getByLabel("Filter by kind").selectOption("all")
  await page.reload()
  await expect(counts).toContainText("1 changed since")
  await expect(row).toHaveAttribute("data-state", "stale")
  await page.getByRole("button", { name: "Update the 1 changed" }).click()
  await expect(counts).toContainText("0 changed since", { timeout: 30_000 })
  await expect(row).toHaveAttribute("data-state", "described")
})

test("the agent's plan becomes cards of the board, which are then moved by dragging", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}`)

  const plan = page.getByRole("region", { name: "Plan", exact: true })
  await plan.getByRole("button", { name: "Ask the agent to plan…" }).click()
  await plan.getByRole("button", { name: "Ask for a plan" }).click()

  const sweep = page.getByRole("article", { name: "Run the stability sweep" })
  await expect(column(page, "Planned").getByRole("article")).toHaveCount(1)
  await expect(sweep).toHaveAttribute("data-origin", "agent")
  await expect(sweep.getByText("agent", { exact: true })).toBeVisible()
  await expect(
    column(page, "Backlog").getByRole("article", { name: "The scheme is first order in time" }),
  ).toBeVisible()
  await expect(plan).toContainText("Last plan of the agent: 2 card(s) added, 0 changed")
  await expect(plan).toContainText("Check stability first, then accuracy.")
  await page.screenshot({ path: "test-results/screens/plan.png", fullPage: true })

  // Dragged by its handle to another column: the plan is the researcher's to change.
  const handle = sweep.getByRole("button", { name: "Drag Run the stability sweep" })
  const from = (await handle.boundingBox())!
  const to = (await column(page, "Active").boundingBox())!
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(to.x + to.width / 2, to.y + 60, { steps: 12 })
  await page.mouse.up()
  await expect(
    column(page, "Active").getByRole("article", { name: "Run the stability sweep" }),
  ).toBeVisible()
  await expect(column(page, "Planned").getByRole("article")).toHaveCount(0)
  await page.reload()
  await expect(
    column(page, "Active").getByRole("article", { name: "Run the stability sweep" }),
  ).toBeVisible()
})
