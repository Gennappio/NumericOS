import { mkdirSync } from "node:fs"
import { expect, test, type Page } from "@playwright/test"
import { cardTitles, cli, column, type ProjectRecord } from "./helpers"
import { API_URL } from "./urls"

const OUTPUT = "test-results/walkthrough"

/** Finished animations only: a screenshot must show what a person sees at rest. */
async function capture(page: Page, name: string, fullPage = true) {
  await page.screenshot({ path: `${OUTPUT}/${name}.png`, fullPage, animations: "disabled" })
}

// The M0 journey on the real GUI and a real API: explicitly seeded, clearly marked demo data,
// then create, move and reload. The screenshots are the visual evidence of the M0 gate
// (docs/milestones/M0-gate.md); run this spec alone for a workspace with only the demo project.
test("demo walkthrough: create, move, reload", async ({ page }) => {
  mkdirSync(OUTPUT, { recursive: true })
  const seeded = cli<{ project: ProjectRecord }>("seed-demo")

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto("/")
  await expect(page.getByRole("link", { name: /Demo: 2D heat equation/ }).first()).toBeVisible()
  await capture(page, "01-projects")

  await page.goto(`/projects/${seeded.project.id}`)
  await expect(page.getByText("Demo data").first()).toBeVisible()
  await expect(page.getByRole("status", { name: "Live updates" })).toHaveAttribute(
    "data-transport",
    "live",
  )
  await expect(column(page, "Active").getByRole("article")).toHaveCount(1)
  await capture(page, "02-board-seeded")

  // Create a typed card through the dialog...
  await page.getByRole("button", { name: "New card" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Title").fill("H02: halving the mesh size quarters the L2 error")
  await dialog.getByLabel("Type").selectOption("hypothesis")
  await expect(dialog).toHaveCSS("opacity", "1")
  await capture(page, "03-new-card-dialog", false)
  await dialog.getByRole("button", { name: "Create card" }).click()
  await expect(dialog).toBeHidden()
  const created = column(page, "Backlog").getByRole("article", { name: /^H02/ })
  await expect(created).toBeVisible()

  // ...move it to another column...
  await created.getByLabel(/Workflow status of/).selectOption("review")
  await expect(column(page, "Review").getByRole("article", { name: /^H02/ })).toBeVisible()
  const review = await cardTitles(column(page, "Review"))
  const events = page.getByRole("region", { name: "Recent events" }).getByRole("listitem")
  await expect(events.first()).toContainText("Card moved")
  const ledger = await events.allTextContents()

  // ...and reload: the board and the ledger are exactly as they were.
  await page.reload()
  await expect.poll(() => cardTitles(column(page, "Review"))).toEqual(review)
  await expect(events).toHaveText(ledger)
  await capture(page, "04-board-after-create-move-reload")

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(column(page, "Backlog")).toBeVisible()
  await capture(page, "05-board-narrow")

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.route(`${API_URL}/**`, (route) => route.abort("connectionrefused"))
  await expect(page.getByRole("status", { name: "Backend connection" })).toHaveAttribute(
    "data-state",
    "unreachable",
    { timeout: 20_000 },
  )
  await capture(page, "06-backend-unreachable", false)
})
