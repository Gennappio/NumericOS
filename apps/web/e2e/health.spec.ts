import { expect, test } from "@playwright/test"
import { API_URL } from "./urls"

test("the shell shows the real backend connection state", async ({ page }) => {
  await page.goto("/")

  const status = page.getByRole("status", { name: "Backend connection" })
  await expect(status).toHaveAttribute("data-state", "connected")
  await expect(status).toContainText("Connected")
  await expect(page.getByRole("alert")).toHaveCount(0)

  await expect(page.getByRole("link", { name: "Board" })).toBeVisible()
  for (const view of ["Experiments", "Timeline", "Agents", "Knowledge"]) {
    await expect(page.getByRole("button", { name: new RegExp(`^${view}`) })).toBeDisabled()
  }
})

test("an unreachable backend is reported instead of stale success", async ({ page }) => {
  await page.route(`${API_URL}/**`, (route) => route.abort("connectionrefused"))
  await page.goto("/")

  const status = page.getByRole("status", { name: "Backend connection" })
  await expect(status).toHaveAttribute("data-state", "unreachable")
  await expect(page.getByRole("alert")).toContainText("not reachable")
})
