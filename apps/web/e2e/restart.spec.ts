import { spawn, type ChildProcess } from "node:child_process"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { expect, test, type APIRequestContext } from "@playwright/test"
import { addCard, cardTitles, column, createProject } from "./helpers"
import { API_URL, RESTART_API_PORT, RESTART_API_URL, WEB_URL } from "./urls"

const REPO_ROOT = join("..", "..")

/** A real API process on its own port and data directory, so the test can stop and start it. */
function startApi(dataDir: string): ChildProcess {
  return spawn(
    join(".venv", "bin", "python"),
    ["-m", "numericos", "serve", "--port", String(RESTART_API_PORT), "--data-dir", dataDir],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, NUMERICOS_CORS_ORIGINS: JSON.stringify([WEB_URL]) },
      stdio: "ignore",
    },
  )
}

async function untilHealthy(request: APIRequestContext) {
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${RESTART_API_URL}/v1/health`)).status()
        } catch {
          return 0
        }
      },
      { timeout: 30_000 },
    )
    .toBe(200)
}

async function stop(api: ChildProcess) {
  if (api.exitCode !== null || api.signalCode !== null) return
  const exited = new Promise((resolve) => api.once("exit", resolve))
  api.kill("SIGTERM")
  await exited
}

test("an open page survives a restart of the API process and continues from the same ledger", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  const dataDir = mkdtempSync(join(tmpdir(), "numericos-restart-"))
  let api = startApi(dataDir)
  try {
    await untilHealthy(request)
    // This page talks to the API process under test instead of the shared one.
    await page.route(`${API_URL}/**`, (route) =>
      route.continue({ url: route.request().url().replace(API_URL, RESTART_API_URL) }),
    )
    const project = await createProject(request, { name: "Survives restarts" }, RESTART_API_URL)
    await addCard(request, project.id, { title: "Stays in backlog" }, RESTART_API_URL)
    await addCard(request, project.id, { title: "H01", type: "hypothesis" }, RESTART_API_URL)

    await page.goto(`/projects/${project.id}`)
    const connection = page.getByRole("status", { name: "Backend connection" })
    const liveUpdates = page.getByRole("status", { name: "Live updates" })
    const eventRows = page.getByRole("region", { name: "Recent events" }).getByRole("listitem")
    await expect(liveUpdates).toHaveAttribute("data-transport", "live")
    await column(page, "Backlog")
      .getByLabel("Workflow status of H01")
      .selectOption("review")
    await expect(column(page, "Review").getByRole("article", { name: "H01" })).toBeVisible()
    await expect(eventRows).toHaveCount(4)
    const recorded = await eventRows.allTextContents()

    await stop(api)

    await expect(connection).toHaveAttribute("data-state", "unreachable", { timeout: 20_000 })
    await expect(liveUpdates).not.toHaveAttribute("data-transport", "live")
    await expect(page.getByRole("alert").filter({ hasText: "not reachable" })).toBeVisible()
    await expect(column(page, "Review").getByRole("article", { name: "H01" })).toBeVisible()
    await expect(page.getByRole("button", { name: "New card" })).toBeDisabled()

    api = startApi(dataDir)
    await untilHealthy(request)

    // No reload: the page finds the backend again and resubscribes by itself.
    await expect(connection).toHaveAttribute("data-state", "connected", { timeout: 20_000 })
    await expect(liveUpdates).toHaveAttribute("data-transport", "live", { timeout: 20_000 })
    await expect(page.getByRole("alert")).toHaveCount(0)
    await expect.poll(() => cardTitles(column(page, "Backlog"))).toEqual(["Stays in backlog"])
    await expect.poll(() => cardTitles(column(page, "Review"))).toEqual(["H01"])
    await expect(eventRows).toHaveText(recorded)

    // The restarted process continues the same ledger and pushes new events again.
    await addCard(request, project.id, { title: "After the restart" }, RESTART_API_URL)
    await expect(
      column(page, "Backlog").getByRole("article", { name: "After the restart" }),
    ).toBeVisible({ timeout: 2_000 })
    await expect(eventRows).toHaveCount(5)
    const positions = (await eventRows.allTextContents()).map((row) =>
      Number(row.match(/^#(\d+)/)?.[1]),
    )
    expect(positions[0]).toBe(positions[1] + 1)

    await page.reload()
    await expect.poll(() => cardTitles(column(page, "Backlog"))).toEqual([
      "Stays in backlog",
      "After the restart",
    ])
    await expect.poll(() => cardTitles(column(page, "Review"))).toEqual(["H01"])
  } finally {
    await stop(api)
    rmSync(dataDir, { recursive: true, force: true })
  }
})
