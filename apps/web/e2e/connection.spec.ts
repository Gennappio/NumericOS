import { expect, test } from "@playwright/test"
import { addCard, column, createProject } from "./helpers"
import { API_URL } from "./urls"

const status = { name: "Backend connection" } as const

test("an unreachable backend is reported instead of an empty workspace", async ({ page }) => {
  await page.route(`${API_URL}/**`, (route) => route.abort("connectionrefused"))
  await page.goto("/")

  await expect(page.getByRole("status", status)).toHaveAttribute("data-state", "unreachable")
  await expect(page.getByText("Could not load projects")).toBeVisible()
  await expect(page.getByRole("button", { name: "New project" })).toBeDisabled()
  await expect(page.getByRole("heading", { name: "No projects yet" })).toHaveCount(0)
})

test("losing the backend keeps the last state visible, marks it and locks changes", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  await addCard(request, project.id, { title: "Seen before the outage" })
  await page.goto(`/projects/${project.id}`)
  const card = column(page, "Backlog").getByRole("article", { name: "Seen before the outage" })
  await expect(card).toBeVisible()
  await expect(page.getByRole("status", status)).toHaveAttribute("data-state", "connected")

  await page.route(`${API_URL}/**`, (route) => route.abort("connectionrefused"))

  await expect(page.getByRole("status", status)).toHaveAttribute("data-state", "unreachable", {
    timeout: 20_000,
  })
  await expect(page.getByRole("alert").filter({ hasText: "not reachable" })).toContainText(
    "last state received at",
  )
  // No part of the page may still claim to be live.
  await expect(page.getByRole("status", { name: "Live updates" })).not.toHaveAttribute(
    "data-transport",
    "live",
  )
  await expect(card).toBeVisible()
  await expect(page.getByRole("button", { name: "New card" })).toBeDisabled()
  await expect(page.getByRole("button", { name: "Edit project" })).toBeDisabled()
  await expect(card.getByLabel(/Workflow status of/)).toBeDisabled()

  await page.unroute(`${API_URL}/**`)

  await expect(page.getByRole("status", status)).toHaveAttribute("data-state", "connected", {
    timeout: 20_000,
  })
  await expect(page.getByRole("button", { name: "New card" })).toBeEnabled()
  await expect(page.getByRole("alert")).toHaveCount(0)
})
