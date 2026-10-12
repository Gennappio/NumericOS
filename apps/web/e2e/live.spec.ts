import { expect, test, type Page } from "@playwright/test"
import { addCard, column, createProject } from "./helpers"
import { API_URL } from "./urls"

const liveUpdates = (page: Page) => page.getByRole("status", { name: "Live updates" })
const events = (page: Page) => page.getByRole("region", { name: "Recent events" })
const eventRows = (page: Page) => events(page).getByRole("listitem")

/** Lets everything through except the Server-Sent Events request of the event stream. */
async function blockEventStream(page: Page) {
  await page.route(`${API_URL}/v1/events?**`, (route) =>
    route.request().headers()["accept"]?.includes("text/event-stream")
      ? route.abort("connectionrefused")
      : route.fallback(),
  )
}

test("a change made by another client is pushed to the page at once", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  await page.goto(`/projects/${project.id}`)
  await expect(liveUpdates(page)).toHaveAttribute("data-transport", "live")
  await expect(column(page, "Planned").getByText("No cards")).toBeVisible()

  await addCard(request, project.id, { title: "Added by a script", workflow_status: "planned" })

  // Well inside the 5 s polling interval: only the event stream can be this fast.
  await expect(
    column(page, "Planned").getByRole("article", { name: "Added by a script" }),
  ).toBeVisible({ timeout: 2_000 })
  await expect(eventRows(page).first()).toContainText(
    'Card created: "Added by a script" in Planned',
    { timeout: 2_000 },
  )
})

test("the strip replays what the ledger recorded, newest first, with who did it", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  await page.goto(`/projects/${project.id}`)
  await expect(eventRows(page)).toHaveText([/Project created.*api:unknown/])

  await page.getByRole("button", { name: "New card" }).click()
  await page.getByRole("dialog").getByLabel("Title").fill("H01")
  await page.getByRole("dialog").getByRole("button", { name: "Create card" }).click()
  await column(page, "Backlog").getByLabel(/Workflow status of/).selectOption("review")
  await expect(column(page, "Review").getByRole("article", { name: "H01" })).toBeVisible()

  await expect(eventRows(page)).toHaveText([
    /Card moved: "H01" from Backlog to Review.*web:local/,
    /Card created: "H01" in Backlog.*web:local/,
    /Project created.*api:unknown/,
  ])

  // The strip shows the ledger, so a reload shows the same entries in the same order.
  await page.reload()
  await expect(eventRows(page)).toHaveText([
    /Card moved: "H01" from Backlog to Review/,
    /Card created: "H01" in Backlog/,
    /Project created/,
  ])
  const positions = await eventRows(page).evaluateAll((rows) =>
    rows.map((row) => Number(row.textContent?.match(/^#(\d+)/)?.[1])),
  )
  expect(positions).toEqual([...positions].sort((a, b) => b - a))
})

test("without the stream the page says so, keeps up by polling and returns to live", async ({
  page,
  request,
}) => {
  const project = await createProject(request)
  await blockEventStream(page)
  await page.goto(`/projects/${project.id}`)

  await expect(liveUpdates(page)).toHaveAttribute("data-transport", "reconnecting")
  await expect(liveUpdates(page)).toContainText("refreshing every 5 s")
  await expect(page.getByRole("status", { name: "Backend connection" })).toHaveAttribute(
    "data-state",
    "connected",
  )

  await addCard(request, project.id, { title: "Seen through polling" })
  await expect(
    column(page, "Backlog").getByRole("article", { name: "Seen through polling" }),
  ).toBeVisible()

  await page.unroute(`${API_URL}/v1/events?**`)
  await expect(liveUpdates(page)).toHaveAttribute("data-transport", "live")

  await addCard(request, project.id, { title: "Pushed again" })
  await expect(
    column(page, "Backlog").getByRole("article", { name: "Pushed again" }),
  ).toBeVisible({ timeout: 2_000 })
})

test("switching project follows the other project's ledger", async ({ page, request }) => {
  const first = await createProject(request)
  const second = await createProject(request)
  await addCard(request, second.id, { title: "Belongs to the second" })
  await page.goto(`/projects/${first.id}`)
  await expect(liveUpdates(page)).toHaveAttribute("data-transport", "live")
  await expect(eventRows(page)).toHaveCount(1)

  await page.getByRole("navigation", { name: "Projects" }).getByRole("link", { name: second.name }).click()

  await expect(page.getByRole("heading", { level: 1, name: second.name })).toBeVisible()
  await expect(liveUpdates(page)).toHaveAttribute("data-transport", "live")
  await expect(eventRows(page)).toHaveText([
    /Card created: "Belongs to the second"/,
    /Project created/,
  ])
  await addCard(request, first.id, { title: "Not shown here" })
  await addCard(request, second.id, { title: "Shown here" })
  await expect(column(page, "Backlog").getByRole("article", { name: "Shown here" })).toBeVisible({
    timeout: 2_000,
  })
  await expect(page.getByRole("article", { name: "Not shown here" })).toHaveCount(0)
})
