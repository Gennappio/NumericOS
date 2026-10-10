import { mkdirSync } from "node:fs"
import { expect, test, type Page } from "@playwright/test"
import { cli, column, type ProjectRecord } from "./helpers"
import { API_URL } from "./urls"

const OUTPUT = "test-results/walkthrough"

/** Finished animations only: a screenshot must show what a person sees at rest. */
async function capture(page: Page, name: string, fullPage = true) {
  await page.screenshot({ path: `${OUTPUT}/${name}.png`, fullPage, animations: "disabled" })
}

// Captures the real GUI on real (explicitly seeded, clearly marked) demo data, for visual review.
test("demo walkthrough screenshots", async ({ page }) => {
  mkdirSync(OUTPUT, { recursive: true })
  const seeded = cli<{ project: ProjectRecord }>("seed-demo")

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto("/")
  await expect(page.getByRole("link", { name: /Demo: 2D heat equation/ }).first()).toBeVisible()
  await capture(page, "01-projects")

  await page.goto(`/projects/${seeded.project.id}`)
  await expect(page.getByText("Demo data").first()).toBeVisible()
  await expect(column(page, "Active").getByRole("article")).toHaveCount(1)
  await capture(page, "02-board-desktop")

  await page.getByRole("button", { name: "New card" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveCSS("opacity", "1")
  await capture(page, "03-new-card-dialog", false)
  await page.keyboard.press("Escape")
  await expect(dialog).toBeHidden()

  await column(page, "Active").getByRole("button", { name: /^H01/, exact: false }).first().click()
  await expect(dialog).toHaveCSS("opacity", "1")
  await capture(page, "04-edit-card-dialog", false)
  await page.keyboard.press("Escape")
  await expect(dialog).toBeHidden()

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
