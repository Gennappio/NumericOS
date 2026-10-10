import { expect, test } from "@playwright/test"
import { cli, uniqueName, type ProjectRecord } from "./helpers"

// Runs first (see playwright.config.ts): the API starts with an empty database.

test("an empty workspace explains itself and a project can be created from the GUI", async ({
  page,
}) => {
  await page.goto("/")

  await expect(page.getByRole("status", { name: "Backend connection" })).toHaveAttribute(
    "data-state",
    "connected",
  )
  await expect(page.getByRole("heading", { name: "No projects yet" })).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)

  const name = uniqueName("Heat 2D")
  await page.getByRole("button", { name: "New project" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByLabel("Name")).toBeFocused()
  await dialog.getByLabel("Name").fill(name)
  await dialog
    .getByLabel("Research question")
    .fill("Which time steps keep the explicit scheme stable?")
  await dialog.getByLabel("Code reference").fill("/work/heat2d")
  await dialog.getByRole("button", { name: "Create project" }).click()

  await expect(page).toHaveURL(/\/projects\/prj_[0-9A-Z]{26}$/)
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible()
  await expect(page.getByText("Which time steps keep the explicit scheme stable?")).toBeVisible()
  await expect(page.getByText("/work/heat2d")).toBeVisible()
  await expect(page.getByRole("navigation", { name: "Projects" }).getByRole("link", { name }))
    .toBeVisible()

  // The same project is visible to a scripted client through the CLI.
  const listed = cli<{ projects: ProjectRecord[] }>("project", "list")
  expect(listed.projects.map((project) => project.name)).toEqual([name])
})

test("a relative code reference is rejected with the server's message", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "New project" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Name").fill(uniqueName("Invalid"))
  await dialog.getByLabel("Code reference").fill("relative/path")
  await dialog.getByRole("button", { name: "Create project" }).click()

  await expect(dialog.getByRole("alert")).toContainText("absolute path")
  await expect(dialog).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
})
