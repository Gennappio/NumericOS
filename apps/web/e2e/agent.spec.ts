import { expect, test } from "@playwright/test"
import { trustedExampleProject } from "./helpers"

/**
 * Conversations with the agent in the browser, end to end: a real supervisor starts the agent
 * command (the stand-in for Claude Code that the test servers are configured with) and the page
 * shows what was observed of it.
 */

test("a conversation is held inside the project and the answer is rendered", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("navigation", { name: "Project views" }).getByText("Agent").click()

  await expect(page.getByText(/Start a conversation to ask the agent/)).toBeVisible()
  await page.getByRole("button", { name: "New conversation" }).click()
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible()
  await page
    .getByLabel("Message to the agent")
    .fill("Explain the scheme.\nREAD examples/heat2d-python/experiment.yaml")
  await page.getByRole("button", { name: "Send" }).click()

  // The prompt is recorded at once; the answer is a turn that a supervisor serves.
  await expect(page.getByRole("article", { name: "Your message" })).toContainText(
    "Explain the scheme.",
  )
  const answer = page.getByRole("article", { name: "Agent answer" })
  await expect(answer.locator("[data-status=final]")).toHaveText("Answered")
  await expect(answer).toContainText("You asked: Explain the scheme.")
  await expect(answer.locator(".katex-display")).toBeVisible()
  await expect(answer.getByText("0.012 USD")).toBeVisible()
  await expect(answer.getByText("model fake-model")).toBeVisible()
  await answer.getByText(/What the agent did/).click()
  const actions = answer.getByRole("list", { name: "Actions of the agent" })
  await expect(actions.getByText("Read")).toBeVisible()
  await expect(actions.getByText(/experiment\.yaml/)).toBeVisible()
  await expect(actions.getByRole("img", { name: "Tool succeeded" })).toBeVisible()

  // The conversation is named after the first prompt and persists across a reload.
  const conversations = page.getByRole("navigation", { name: "Conversations" })
  await expect(conversations.getByRole("link", { name: /Explain the scheme/ })).toHaveAttribute(
    "aria-current",
    "page",
  )
  await page.reload()
  await expect(page.getByRole("article", { name: "Agent answer" })).toContainText(
    "You asked: Explain the scheme.",
  )
  await page.screenshot({ path: "test-results/screens/agent-answer.png", fullPage: true })
})

test("what the permission mode refuses is shown, and a working turn can be stopped", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/agent`)
  await page.getByLabel("starting in mode").selectOption({ label: "Read only" })
  await page.getByRole("button", { name: "New conversation" }).click()
  await expect(page.getByLabel("Permission mode")).toHaveValue("read_only")

  await page.getByLabel("Message to the agent").fill("WRITE notes.txt::hello")
  await page.getByRole("button", { name: "Send" }).click()
  const first = page.getByRole("article", { name: "Agent answer" }).first()
  await expect(first.locator("[data-status=final]")).toBeVisible()
  const refused = first.getByRole("region", { name: "Refused by the permission mode" })
  await expect(refused).toContainText("Write")
  await expect(refused).toContainText("notes.txt")

  await page.getByLabel("Message to the agent").fill("SLEEP 60")
  await page.getByRole("button", { name: "Send" }).click()
  const second = page.getByRole("article", { name: "Agent answer" }).nth(1)
  await expect(second.locator("[data-status=running]")).toBeVisible()
  await expect(page.getByLabel("Message to the agent")).toBeDisabled() // one turn at a time
  await second.getByRole("button", { name: "Stop the agent…" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Why (recorded with the turn)").fill("seen enough")
  await dialog.getByRole("button", { name: "Stop the agent" }).click()

  await expect(second.locator("[data-status=cancelled]")).toHaveText("Stopped")
  await expect(second.getByRole("alert")).toContainText("Stopped: seen enough")
  await expect(page.getByLabel("Message to the agent")).toBeEnabled()
  await page.screenshot({ path: "test-results/screens/agent-stopped.png", fullPage: true })
})
