import { expect, test } from "@playwright/test"
import { addCard, cardTitles, column, createProject } from "./helpers"
import { API_URL } from "./urls"

test("a hypothesis card is created, moved to another column and survives a reload", async ({
  page,
  request,
}) => {
  const project = await createProject(request, {
    research_question: "Is the explicit scheme stable at dt = 0.01?",
  })
  await page.goto(`/projects/${project.id}`)
  await expect(page.getByRole("heading", { level: 1, name: project.name })).toBeVisible()
  await expect(page.getByText("Is the explicit scheme stable at dt = 0.01?")).toBeVisible()

  await page.getByRole("button", { name: "New card" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Title").fill("H01: smaller dt restores stability")
  await dialog.getByLabel("Type").selectOption("hypothesis")
  await dialog.getByLabel("Description").fill("Prediction: residual growth disappears.")
  await dialog.getByRole("button", { name: "Create card" }).click()
  await expect(dialog).toBeHidden()

  const card = column(page, "Backlog").getByRole("article", { name: /^H01/ })
  await expect(card).toBeVisible()
  await expect(card).toContainText("Hypothesis")

  await card.getByLabel(/Workflow status of/).selectOption("review")
  const moved = column(page, "Review").getByRole("article", { name: /^H01/ })
  await expect(moved).toBeVisible()
  await expect(column(page, "Backlog").getByRole("article")).toHaveCount(0)

  await page.reload()
  await expect(moved).toBeVisible()
  await expect(moved.getByLabel(/Workflow status of/)).toHaveValue("review")
  await expect(column(page, "Backlog").getByRole("article")).toHaveCount(0)
})

test("the order inside a column is durable", async ({ page, request }) => {
  const project = await createProject(request)
  for (const title of ["first", "second", "third"]) {
    await addCard(request, project.id, { title })
  }
  await page.goto(`/projects/${project.id}`)
  const backlog = column(page, "Backlog")
  await expect.poll(() => cardTitles(backlog)).toEqual(["first", "second", "third"])

  await backlog.getByRole("button", { name: "Move third up" }).click()
  await expect.poll(() => cardTitles(backlog)).toEqual(["first", "third", "second"])
  await backlog.getByRole("button", { name: "Move third up" }).click()
  await expect.poll(() => cardTitles(backlog)).toEqual(["third", "first", "second"])
  await expect(backlog.getByRole("button", { name: "Move third up" })).toBeDisabled()
  await backlog.getByRole("button", { name: "Move first down" }).click()
  await expect.poll(() => cardTitles(backlog)).toEqual(["third", "second", "first"])

  await page.reload()
  await expect.poll(() => cardTitles(backlog)).toEqual(["third", "second", "first"])
})

test("a card is edited in place and the change is durable", async ({ page, request }) => {
  const project = await createProject(request)
  await addCard(request, project.id, { title: "Draft title", type: "issue" })
  await page.goto(`/projects/${project.id}`)

  await page.getByRole("button", { name: "Draft title", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByRole("heading", { name: "Edit card" })).toBeVisible()
  await expect(dialog.getByLabel("Type")).toHaveValue("issue")
  await expect(dialog).toContainText("version 1")
  await dialog.getByLabel("Title").fill("Wrong boundary condition at the right wall")
  await dialog.getByLabel("Workflow status").selectOption("active")
  await dialog.getByRole("button", { name: "Save card" }).click()
  await expect(dialog).toBeHidden()

  const card = column(page, "Active").getByRole("article", { name: /^Wrong boundary/ })
  await expect(card).toBeVisible()
  await page.reload()
  await expect(card).toBeVisible()
  await expect(card).toContainText("Issue")
})

test("moving a card to Completed states no scientific verdict", async ({ page, request }) => {
  const project = await createProject(request)
  await addCard(request, project.id, { title: "H02: CSR beats dense", type: "hypothesis" })
  await page.goto(`/projects/${project.id}`)

  await column(page, "Backlog").getByLabel(/Workflow status of/).selectOption("completed")

  const card = column(page, "Completed").getByRole("article", { name: /^H02/ })
  await expect(card).toBeVisible()
  await expect(card).not.toContainText(/supported|refuted|validated|confirmed|passed/i)
})

test("a stale edit is refused and explained instead of overwriting newer work", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  const card = await addCard(request, project.id, { title: "Contested" })
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("button", { name: "Contested", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Title").fill("My edit")

  // Somebody else changes the card while the dialog is open.
  const other = await request.patch(`${API_URL}/v1/cards/${card.id}`, {
    data: { version: card.version, title: "Their edit" },
  })
  expect(other.status()).toBe(200)

  await dialog.getByRole("button", { name: "Save card" }).click()

  await expect(dialog.getByRole("alert")).toContainText("changed elsewhere")
  await dialog.getByRole("button", { name: "Cancel" }).click()
  await expect(column(page, "Backlog").getByRole("article", { name: "Their edit" })).toBeVisible()
})

test("the board is usable from the keyboard", async ({ page, request }) => {
  const project = await createProject(request)
  await page.goto(`/projects/${project.id}`)
  const newCard = page.getByRole("button", { name: "New card" })

  await newCard.focus()
  await page.keyboard.press("Enter")
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByLabel("Title")).toBeFocused()
  await page.keyboard.type("Typed without a mouse")
  await page.keyboard.press("Enter")
  await expect(dialog).toBeHidden()
  await expect(column(page, "Backlog").getByRole("article", { name: "Typed without a mouse" }))
    .toBeVisible()

  await newCard.focus()
  await page.keyboard.press("Enter")
  await expect(dialog).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(dialog).toBeHidden()
  await expect(newCard).toBeFocused()
})

test("views of later milestones are visibly unavailable, never pretend-functional", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  await page.goto(`/projects/${project.id}`)

  const views = page.getByRole("navigation", { name: "Project views" })
  await expect(views.getByText("Board")).toHaveAttribute("aria-current", "page")
  for (const view of ["Experiments", "Timeline", "Agents", "Knowledge"]) {
    await expect(views.getByRole("button", { name: new RegExp(`^${view}`) })).toBeDisabled()
  }
})

test("an unknown project is reported as such", async ({ page }) => {
  await page.goto("/projects/prj_01J9W2Z4K7QX8YB3N5M6T0R1S2")

  await expect(page.getByRole("heading", { name: "Project not found" })).toBeVisible()
  await page.getByRole("link", { name: "Back to all projects" }).click()
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible()
})
