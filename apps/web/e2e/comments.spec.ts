import { readFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test } from "@playwright/test"
import { selectPassage, trustedExampleProject } from "./helpers"

/**
 * Comments on what the agent wrote, in the browser, end to end: a passage is selected and
 * commented, Clarify answers next to the passage without touching the text, Resolve makes the
 * agent edit the files and rewrite the text. The agent is the stand-in of the test servers.
 */

const SOLVER = "examples/heat2d-python/heat2d.py"

test("a passage of the theory is commented, clarified in place and then changed", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/theory`)
  await page.getByLabel("Instructions for the agent").fill(`READ ${SOLVER}`)
  await page.getByRole("button", { name: "Write the theory" }).click()
  const paper = page.getByRole("article", { name: "Explicit scheme for the 2D heat equation" })
  await expect(paper.getByRole("heading", { level: 1 })).toBeVisible()
  const comments = page.getByRole("complementary", { name: "Comments" })
  await expect(comments.getByText(/Select any passage of the text/)).toBeVisible()
  await expect(comments.getByRole("button", { name: "Clarify (0)" })).toBeDisabled()

  // A clarification request on an exact passage.
  await selectPassage(paper, "homogeneous Dirichlet")
  const bar = page.getByRole("dialog", { name: "Comment on the selected passage" })
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  await bar.getByLabel("What is not clear about this passage?").fill("Why homogeneous?")
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  const question = comments.getByRole("article", { name: "Clarification: homogeneous Dirichlet" })
  await expect(question).toHaveAttribute("data-status", "open")
  await expect(question).toContainText("Why homogeneous?")
  // The passage is highlighted on the page, which is not rewritten for it.
  expect(await page.evaluate(() => CSS.highlights.has("nos-focus"))).toBe(true)

  // A change request on another passage, and a note on a word picked with the pointer.
  await selectPassage(paper, "Forward Euler")
  await bar.getByRole("button", { name: "Request a change" }).click()
  await bar.getByRole("textbox").fill("Make the scheme implicit.")
  await bar.getByRole("button", { name: "Request a change" }).click()
  const change = comments.getByRole("article", { name: "Change request: Forward Euler" })
  await expect(change).toHaveAttribute("data-status", "open")
  await paper.getByText("The temperature").dblclick({ position: { x: 20, y: 8 } })
  await bar.getByRole("button", { name: "Add a note" }).click()
  await bar.getByRole("textbox").fill("check the units")
  await bar.getByRole("button", { name: "Add a note" }).click()
  await expect(comments.getByRole("article", { name: /^Note:/ })).toContainText("check the units")
  await expect(comments.getByRole("heading", { name: "Comments 3" })).toBeVisible()

  // Clarify: every clarification in one turn; the answer appears next to its passage.
  await comments.getByRole("button", { name: "Clarify (1)" }).click()
  await expect(question).toHaveAttribute("data-status", "answered")
  const inline = paper.getByRole("complementary", {
    name: "Clarification of: homogeneous Dirichlet",
  })
  await expect(inline).toContainText('About "homogeneous Dirichlet": the bound comes from')
  await expect(inline.locator(".katex").first()).toBeVisible()
  // It sits right after the paragraph of the passage, before the next section.
  const order = await paper.evaluate((root) =>
    [...root.querySelector(".paper")!.children].map((node) =>
      node.hasAttribute("data-slot") ? "CLARIFICATION" : node.textContent!.slice(0, 18),
    ),
  )
  const at = order.indexOf("CLARIFICATION")
  expect(order[at - 1]).toBe("with homogeneous D")
  expect(order[at + 1]).toBe("Numerical method")
  await expect(page.getByText("Version 1 · written by fake-model")).toBeVisible() // text untouched
  await expect(change).toHaveAttribute("data-status", "open") // Clarify left the change alone
  await page.screenshot({ path: "test-results/screens/comments-clarified.png", fullPage: true })

  // Resolve: the change requests in one turn; the agent edits the file and rewrites the text.
  await comments.getByRole("button", { name: "Resolve (1)…" }).click()
  const dialog = page.getByRole("dialog", { name: "Resolve 1 change request" })
  await expect(dialog).toContainText("It edits the files of the project directly")
  await dialog
    .getByLabel(/Instructions for the agent/)
    .fill(`WRITE ${SOLVER}::print('implicit now')\nREPLACE Forward Euler=>Backward Euler`)
  await dialog.getByRole("button", { name: "Resolve" }).click()
  await expect(change).toHaveAttribute("data-status", "resolved")
  await expect(change).toContainText('Changed what "Forward Euler" says')
  await expect(page.getByText("Version 2 · written by fake-model")).toBeVisible()
  await expect(paper).toContainText("Backward Euler in time")
  expect(readFileSync(join(project.root_path!, SOLVER), "utf8")).toBe("print('implicit now')")
  // The text is current with the file the agent changed: nothing is marked as out of date.
  await expect(page.getByText(/changed since/)).toHaveCount(0)
  // The clarification is still next to its passage in the new text; the request's passage
  // was rewritten, and its comment says so.
  await expect(inline).toBeVisible()
  await expect(change).toHaveAttribute("data-anchor", "detached")
  await expect(change).toContainText("passage no longer in the text")
  await page.reload()
  await expect(question).toHaveAttribute("data-status", "answered")
  await expect(inline).toBeVisible()
  await page.screenshot({ path: "test-results/screens/comments-resolved.png", fullPage: true })
})

test("an answer in a conversation is commented under it, and a comment can be withdrawn", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/agent`)
  await page.getByRole("button", { name: "New conversation" }).click()
  await page.getByLabel("Message to the agent").fill("Is the scheme stable?")
  await page.getByRole("button", { name: "Send" }).click()
  const answer = page.getByRole("article", { name: "Agent answer" })
  await expect(answer.locator("[data-status=final]")).toBeVisible()
  await expect(answer.getByRole("complementary", { name: "Comments" })).toHaveCount(0)

  await selectPassage(answer.locator("[data-commentable]"), "explicit scheme")
  const bar = page.getByRole("dialog", { name: "Comment on the selected passage" })
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  await bar.getByRole("textbox").fill("Which one?")
  await bar.getByRole("button", { name: "Ask to clarify" }).click()
  const comments = answer.getByRole("complementary", { name: "Comments" })
  const comment = comments.getByRole("article", { name: "Clarification: explicit scheme" })
  await expect(comment).toContainText("Which one?")

  await comments.getByRole("button", { name: "Clarify (1)" }).click()
  await expect(comment).toHaveAttribute("data-status", "answered")
  await expect(
    answer.locator("[data-commentable]").getByRole("complementary", { name: /Clarification of/ }),
  ).toContainText("the bound comes from")
  // The conversation did not grow: the clarification has a session of its own.
  await expect(page.getByRole("article", { name: "Your message" })).toHaveCount(1)
  await expect(page.getByRole("article", { name: "Agent answer" })).toHaveCount(1)

  await selectPassage(answer.locator("[data-commentable]"), "You asked")
  await bar.getByRole("button", { name: "Add a note" }).click()
  await bar.getByRole("button", { name: "Add a note" }).click() // a note may be empty
  const note = comments.getByRole("article", { name: "Note: You asked" })
  await note.getByRole("button", { name: "Withdraw" }).click()
  await expect(note).toHaveCount(0)
  await expect(comments.getByRole("heading", { name: "Comments 1" })).toBeVisible()
})
