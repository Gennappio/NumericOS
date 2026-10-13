import { expect, test } from "@playwright/test"
import { startConversation, trustedExampleProject } from "./helpers"

/**
 * Conversations with the agent in the browser, end to end: a real supervisor starts the agent
 * command (the stand-in for Claude Code that the test servers are configured with) and the page
 * shows what was observed of it.
 */

test("a conversation is started from the sidebar and held inside the project's page", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}`)
  const sidebar = page.getByRole("navigation", { name: "Projects" })
  const views = page.getByRole("navigation", { name: "Project views" })
  await expect(sidebar.getByText("No conversation yet: start one with +.")).toBeVisible()

  await sidebar.getByRole("button", { name: `New conversation in ${project.name}` }).click()
  await expect(page).toHaveURL(new RegExp(`/projects/${project.id}/conversations/ases_`))
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible()
  // Still the one page of the project: its name and its views stay, and none of them is current.
  await expect(page.getByRole("heading", { level: 1, name: project.name })).toBeVisible()
  await expect(views.getByRole("link", { name: "Plan" })).toBeVisible()
  await expect(views.locator("[aria-current=page]")).toHaveCount(0)
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

  // The conversation is named after the first prompt, under the project's name in the sidebar,
  // and persists across a reload.
  const conversations = sidebar.getByRole("list", { name: `Conversations of ${project.name}` })
  const link = conversations.getByRole("link", { name: /Explain the scheme/ })
  await expect(link).toHaveAttribute("aria-current", "page")
  await page.reload()
  await expect(page.getByRole("article", { name: "Agent answer" })).toContainText(
    "You asked: Explain the scheme.",
  )
  await page.screenshot({ path: "test-results/screens/agent-answer.png", fullPage: true })

  // The views of the project are one click away, and so is the way back to the conversation.
  await views.getByRole("link", { name: "Theory" }).click()
  await expect(views.getByText("Theory")).toHaveAttribute("aria-current", "page")
  await expect(link).not.toHaveAttribute("aria-current", "page")
  await link.click()
  await expect(page.getByRole("article", { name: "Agent answer" })).toBeVisible()

  // A second conversation of the same project is listed above the first.
  await sidebar.getByRole("button", { name: `New conversation in ${project.name}` }).click()
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible()
  await expect(page.getByRole("article", { name: "Agent answer" })).toHaveCount(0)
  await expect(conversations.getByRole("link")).toHaveText([
    "New conversation",
    /Explain the scheme/,
  ])
})

test("what the permission mode refuses is shown, and a working turn can be stopped", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await startConversation(page, project)
  await page.getByLabel("Permission mode").selectOption({ label: "Read only" })
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

test("the model and effort of each task are chosen per project and used by the next turn", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("navigation", { name: "Project views" }).getByText("Agent").click()

  // The Agent view is this table and nothing else: the conversations are in the sidebar.
  const table = page.getByRole("table", { name: "Models and effort per task" })
  await expect(page.getByLabel("Message to the agent")).toHaveCount(0)
  await expect(table.getByRole("row")).toHaveCount(8)
  await expect(page.getByLabel("Model for Clarify")).toBeEnabled()
  // Every task has a feature that uses it: a lighter model is suggested where it is enough.
  await expect(page.getByLabel("Model for Pipeline")).toHaveValue("claude-sonnet-5-5")
  await page.getByLabel("Model for Conversation").selectOption("claude-haiku-5-5")
  await page.getByLabel("Effort for Conversation").selectOption("low")
  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled() // saved: no change left

  await page.screenshot({ path: "test-results/screens/agent-policy.png", fullPage: true })

  await startConversation(page, project)
  await expect(page.getByRole("option", { name: "Policy: Haiku 5.5" })).toBeAttached()
  await page.getByLabel("Message to the agent").fill("ECHO light and quick")
  await page.getByRole("button", { name: "Send" }).click()
  const answer = page.getByRole("article", { name: "Agent answer" })
  await expect(answer.locator("[data-status=final]")).toBeVisible()
  await expect(answer.getByText("model claude-haiku-5-5")).toBeVisible()
  await expect(answer.getByText("effort low")).toBeVisible()
  await expect(answer.getByText("12 in / 34 out tokens")).toBeVisible()
  await expect(answer.getByText("plan: 21% of the 5-hour window, 4% of the week")).toBeVisible()

  // A conversation can override its row of the policy.
  await page.getByLabel("Effort", { exact: true }).selectOption("max")
  await page.getByLabel("Message to the agent").fill("ECHO harder")
  await page.getByRole("button", { name: "Send" }).click()
  const second = page.getByRole("article", { name: "Agent answer" }).nth(1)
  await expect(second.locator("[data-status=final]")).toBeVisible()
  await expect(second.getByText("effort max")).toBeVisible()
})
