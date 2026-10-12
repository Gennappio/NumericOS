import { execFileSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test } from "@playwright/test"
import { startConversation, trustedExampleProject } from "./helpers"

/**
 * The repository of a project stays as its author left it: what the agent generates goes to
 * the project's NumericOS folder, which Git does not see, and a new file a turn leaves in the
 * repository is named on the answer and moved out with one click.
 */

function gitStatus(root: string): string {
  return execFileSync("git", ["-C", root, "status", "--porcelain", "--untracked-files=all"], {
    encoding: "utf8",
  }).trim()
}

test("what the agent generates is kept out of the repository, and what it leaves is moved out", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const root = project.root_path!
  await startConversation(page, project)
  await page
    .getByLabel("Message to the agent")
    .fill("Check it.\nSCRATCH check.py::print('ok')\nWRITE notes_from_agent.md::scratch")
  await page.getByRole("button", { name: "Send" }).click()
  const answer = page.getByRole("article", { name: "Agent answer" })
  await expect(answer.locator("[data-status=final]")).toBeVisible()

  // The helper script went to the folder Git ignores; the stray file is named on the answer.
  expect(readFileSync(join(root, ".numericos", "scratch", "check.py"), "utf8")).toBe("print('ok')")
  expect(gitStatus(root)).toBe("?? notes_from_agent.md")
  const box = answer.getByRole("region", { name: "New files in the repository" })
  await expect(box).toContainText("This turn left a new file in the repository")
  await expect(box.getByText("notes_from_agent.md")).toBeVisible()
  await expect(box.getByText("check.py")).toHaveCount(0)
  await page.screenshot({ path: "test-results/screens/agent-created-files.png", fullPage: true })

  await box.getByRole("button", { name: "Move it to the NumericOS folder" }).click()
  await expect(box).toContainText("was moved to the NumericOS folder")
  expect(existsSync(join(root, "notes_from_agent.md"))).toBe(false)
  expect(gitStatus(root)).toBe("") // the repository is as it was before the turn

  // The folder is named where the files of the project are listed, and is not one of them.
  await page.getByRole("navigation", { name: "Project views" }).getByText("Files").click()
  await expect(page.getByLabel("NumericOS folder")).toContainText(".numericos/")
  await expect(page.getByLabel("NumericOS folder")).toContainText("which Git ignores")
  await expect(page.getByTestId("file-counts")).toContainText("files")
  await expect(page.locator('[data-path^=".numericos"]')).toHaveCount(0)
})
