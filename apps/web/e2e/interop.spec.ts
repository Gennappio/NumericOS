import { expect, test } from "@playwright/test"
import { cli, column, uniqueName, type CardRecord, type ProjectRecord } from "./helpers"

test("the CLI and the browser work on the same durable state", async ({ page }) => {
  await page.goto("/")
  const name = uniqueName("From the CLI")

  // CLI -> browser: no reload, the project list refreshes on its own.
  const project = cli<ProjectRecord>("project", "add", name, "--question", "Does it show up?")
  const link = page.getByRole("navigation", { name: "Projects" }).getByRole("link", { name })
  await expect(link).toBeVisible()
  await link.click()
  await expect(page.getByText("Does it show up?")).toBeVisible()

  const card = cli<CardRecord>(
    "card",
    "add",
    "--project",
    project.id,
    "--type",
    "experiment",
    "--title",
    "Run dt sweep",
  )
  await expect(column(page, "Backlog").getByRole("article", { name: "Run dt sweep" }))
    .toBeVisible()

  // Browser -> CLI: a move made in the GUI is what the CLI reads back.
  await column(page, "Backlog").getByLabel(/Workflow status of/).selectOption("active")
  await expect(column(page, "Active").getByRole("article", { name: "Run dt sweep" }))
    .toBeVisible()
  const shown = cli<CardRecord>("card", "show", card.id)
  expect(shown.workflow_status).toBe("active")
  expect(shown.version).toBe(2)

  const ledger = cli<{ events: { type: string; actor: string }[] }>(
    "events",
    "list",
    "--project",
    project.id,
  )
  expect(ledger.events.map((event) => [event.type, event.actor])).toEqual([
    ["PROJECT_CREATED", "cli:local"],
    ["CARD_CREATED", "cli:local"],
    ["CARD_MOVED", "web:local"],
  ])
})
