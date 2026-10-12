import { expect, test } from "@playwright/test"
import { createProject, exampleRepository, queueRun, trustedExampleProject } from "./helpers"

/**
 * Experiments in the browser, end to end: a real supervisor executes the examples of this
 * repository and the pages show what was observed of them.
 */

const HEAT = "examples/heat2d-python/experiment.yaml"
const HEAT_FINE = "examples/heat2d-python/experiment-fine.yaml"

test("an experiment is registered from the repository, run and read back", async ({
  page,
  request,
}) => {
  const root = exampleRepository()
  const project = await createProject(request, { root_path: root })
  await page.goto(`/projects/${project.id}`)
  await page.getByRole("navigation", { name: "Project views" }).getByText("Experiments").click()

  // Nothing runs before the directory is trusted, and the page says who would execute.
  await expect(page.getByText("Not allowed yet")).toBeVisible()
  await expect(page.getByText(/Running: process \d+/)).toBeVisible()
  await page.getByRole("button", { name: "Allow execution in this directory…" }).click()
  const trust = page.getByRole("dialog")
  await expect(trust.getByText(root)).toBeVisible()
  await expect(trust.getByRole("button", { name: "Allow execution" })).toBeDisabled()
  await trust.getByRole("checkbox").check()
  await trust.getByRole("button", { name: "Allow execution" }).click()
  await expect(page.getByText(/^Allowed in/)).toBeVisible()

  // The contract is found as a file of the repository and registered with one click.
  // In the page, not the sidebar: a conversation named after its prompt may carry the path too.
  const contract = page.getByRole("main").getByRole("listitem").filter({ hasText: HEAT }).first()
  await expect(contract.getByText("heat2d-stability")).toBeVisible()
  await contract.getByRole("button", { name: "Register" }).click()
  await expect(contract.getByRole("link", { name: "Registered: open" })).toBeVisible()
  await page.screenshot({ path: "test-results/screens/experiments.png", fullPage: true })
  await page.getByRole("link", { name: "heat2d-stability" }).click()

  await expect(page.getByRole("heading", { name: "heat2d-stability" })).toBeVisible()
  await expect(
    page.getByText("max_abs_u above 1 for 3 consecutive samples: the program is stopped"),
  ).toBeVisible()
  await page.getByLabel("dt").selectOption({ label: "0.0002" })
  await page.getByRole("button", { name: "Queue a run" }).click()

  // The run page: how the process ended, never worded as a verdict on the result.
  await expect(page.locator("[data-status=succeeded]")).toHaveText("Ended normally")
  await expect(page.getByText("no validator has judged the result")).toBeVisible()
  const coverage = page.getByRole("region", { name: "How far the observation reaches" })
  await expect(coverage.locator("[data-coverage=observed]")).toHaveCount(3)
  await expect(coverage.locator("[data-coverage=not_configured]")).toHaveCount(1)

  for (const metric of ["l2_error", "max_abs_u", "norm_l2"]) {
    const chart = page.getByRole("article", { name: `Metric ${metric}` })
    await expect(chart.getByText("61 samples")).toBeVisible()
    await expect(chart.getByRole("img")).toBeVisible()
  }
  await expect(
    page.getByRole("article", { name: "Metric max_abs_u" }).getByText("above 1 stops the run"),
  ).toBeVisible()
  const scalars = page.getByRole("table", { name: "Quantities measured once" })
  await expect(scalars.getByRole("row", { name: /wall_time/ })).toContainText("supervisor")

  await page.getByText("Show the program's output").click()
  await expect(page.getByRole("log", { name: "Program output" })).toContainText("step    600")
  await expect(page.getByRole("log", { name: "Program output" })).not.toContainText(
    "numericos.metric.v1",
  )
  await expect(page.getByRole("link", { name: "outputs/u_final.csv" })).toBeVisible()
  await expect(page.getByText("Run ended, ended normally")).toBeVisible()
  await page.screenshot({ path: "test-results/screens/run-ended-normally.png", fullPage: true })

  // Back on the experiment, the run is a row with its measured values.
  await page.getByRole("link", { name: "heat2d-stability" }).click()
  const row = page.getByRole("table", { name: "Runs of heat2d-stability" }).getByRole("row").nth(1)
  await expect(row).toContainText("Ended normally")
  await expect(row).toContainText("0.0002")
  await page.screenshot({ path: "test-results/screens/experiment.png", fullPage: true })
})

test("a run stopped by a guardrail says why and keeps what was observed", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const run = await queueRun(request, project.id, HEAT, { dt: 0.0003 })
  await page.goto(`/projects/${project.id}/runs/${run.id}`)

  await expect(page.locator("[data-status=failed]")).toHaveText("Failed")
  const alert = page.getByRole("alert").filter({ hasText: "Numerical instability" })
  await expect(alert).toContainText("metric max_abs_u was above 1.0 for 3 consecutive sample(s)")
  await expect(alert).toContainText("this run is evidence")
  await expect(
    page.getByText(/Guardrail: max_abs_u above 1 for 3 consecutive samples .* the program was stopped/),
  ).toBeVisible()
  const chart = page.getByRole("article", { name: "Metric max_abs_u" })
  await expect(chart.getByText("14 samples")).toBeVisible()
  await expect(chart.getByText("above 1 stops the run")).toBeVisible()
  await page.screenshot({ path: "test-results/screens/run-guardrail.png", fullPage: true })
})

test("a run is followed while it goes on and can be stopped from the page", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  const run = await queueRun(request, project.id, HEAT_FINE, { dt: 1.4e-5 })
  await page.goto(`/projects/${project.id}/runs/${run.id}`)

  await expect(page.locator("[data-status=running]")).toBeVisible()
  const chart = page.getByRole("article", { name: "Metric l2_error" })
  const samples = async () =>
    Number((await chart.getByText(/\d+ samples/).textContent())!.match(/(\d+) samples/)![1])
  await expect(chart.getByRole("img")).toBeVisible()
  const early = await samples()
  await expect.poll(samples, { timeout: 15_000 }).toBeGreaterThan(early) // it grows by itself
  await expect(page.getByRole("img", { name: /CPU use over elapsed seconds/ })).toBeVisible()
  await page.screenshot({ path: "test-results/screens/run-in-progress.png", fullPage: true })

  await page.getByRole("button", { name: "Stop the run…" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Why (recorded with the run)").fill("seen enough")
  await dialog.getByRole("button", { name: "Stop the run" }).click()

  await expect(page.locator("[data-status=cancelled]")).toHaveText("Cancelled")
  await expect(page.getByRole("alert").filter({ hasText: "seen enough" })).toBeVisible()
  await expect(page.getByText("Stop requested: seen enough")).toBeVisible()
})
