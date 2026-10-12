import { screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Run } from "@/api/client"
import { ledgerEvent } from "@/test/events"
import { renderProjectView, stubApi } from "@/test/render"
import {
  experimentRecord,
  metricsRecord,
  projectRecord,
  runRecord,
  seriesRecord,
} from "@/test/runs"
import { RunView } from "./RunView"

afterEach(() => vi.unstubAllGlobals())

const EMPTY_FEED = { next_cursor: 0, has_more: false, complete: true }

function open(run: Run, extra: Record<string, unknown> = {}) {
  stubApi({
    "/v1/runs/run_1": run,
    "/v1/runs/run_1/metrics": metricsRecord(),
    "/v1/runs/run_1/events": { events: [], next_cursor: null, has_more: false },
    "/v1/runs/run_1/artifacts": { artifacts: [] },
    "/v1/runs/run_1/resources": { samples: [], ...EMPTY_FEED },
    "/v1/experiments/exp_1": experimentRecord(),
    "/v1/workers": { workers: [], alive: 1 },
    ...extra,
  })
  return renderProjectView("runs/:runId", <RunView />, "/projects/prj_1/runs/run_1", {
    project: projectRecord(),
  })
}

describe("RunView", () => {
  it("shows a normal end as a fact about the process and says nothing judged the result", async () => {
    open(runRecord())

    expect(await screen.findByText("Ended normally")).toBeVisible()
    expect(screen.getByText(/no validator has judged the result/)).toBeVisible()
    expect(screen.queryByRole("alert")).toBeNull()
    expect(screen.getByRole("button", { name: "Run again" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: /Stop the run/ })).toBeNull()
    expect(await screen.findByText("Validators")).toBeVisible()
  })

  it("shows why a run failed and that what was observed is kept", async () => {
    open(
      runRecord({
        status: "failed",
        failure_class: "numerical_instability",
        status_reason: "metric max_abs_u was above 1.0 for 3 consecutive sample(s)",
        exit_code: null,
        exit_signal: "SIGTERM",
      }),
      {
        "/v1/runs/run_1/events": {
          events: [
            ledgerEvent(9, {
              type: "RUN_GUARDRAIL_VIOLATED",
              severity: "error",
              payload: {
                metric: "max_abs_u",
                bound: "above",
                threshold: 1,
                value: 4776.12,
                step: 130,
                consecutive: 3,
                action: "halt",
              },
            }),
          ],
          next_cursor: 9,
          has_more: false,
        },
      },
    )

    const alert = await screen.findByRole("alert")
    expect(within(alert).getByText("Numerical instability")).toBeVisible()
    expect(alert).toHaveTextContent("metric max_abs_u was above 1.0 for 3 consecutive sample(s)")
    expect(alert).toHaveTextContent("this run is evidence")
    expect(screen.getByText("Failed")).toBeVisible()
    expect(screen.getByText(/Ended by SIGTERM/)).toBeVisible()
    expect(screen.queryByText(/no validator has judged/)).toBeNull()
    expect(await screen.findByText(/Guardrail: max_abs_u above 1 for 3 consecutive samples/)).toBeVisible()
  })

  it("offers to stop a run that is going on, and says so once a stop was asked for", async () => {
    const running = runRecord({
      status: "running",
      finished_at: null,
      exit_code: null,
      wall_seconds: null,
    })
    open(running, { "/v1/runs/run_1/resources": { samples: [], ...EMPTY_FEED, complete: false } })

    expect(await screen.findByText("Running")).toBeVisible()
    expect(screen.getByRole("button", { name: "Stop the run…" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: "Run again" })).toBeNull()
    expect(screen.getByText(/Re-read every 2 s while the run goes on/)).toBeVisible()
  })

  it("explains a queued run that no supervisor will start", async () => {
    open(
      runRecord({
        status: "queued",
        started_at: null,
        finished_at: null,
        exit_code: null,
        wall_seconds: null,
        worker_id: null,
        pid: null,
      }),
      { "/v1/workers": { workers: [], alive: 0 } },
    )

    expect(await screen.findByText(/No supervisor is running, so this run stays queued/)).toBeVisible()
    expect(screen.getByText("make worker")).toBeVisible()
  })

  it("shows quantities measured once in a table and series as charts", async () => {
    open(runRecord(), {
      "/v1/runs/run_1/metrics": metricsRecord({
        series: [
          seriesRecord("max_abs_u"),
          seriesRecord("max_rss", {
            unit: "bytes",
            source: "supervisor",
            samples: 1,
            last_value: 18366464,
            last_step: null,
          }),
        ],
      }),
      "/v1/runs/run_1/metrics/max_abs_u/overview": {
        name: "max_abs_u",
        samples: 2,
        buckets: [
          { samples: 1, non_finite: 0, first_step: 0, last_step: 0, first_t: 1, last_t: 1, first_value: 1, last_value: 1, min_value: 1, max_value: 1 },
          { samples: 1, non_finite: 0, first_step: 600, last_step: 600, first_t: 2, last_t: 2, first_value: 0.09, last_value: 0.09, min_value: 0.09, max_value: 0.09 },
        ],
        next_cursor: 80,
        complete: true,
      },
    })

    const chart = await screen.findByRole("article", { name: "Metric max_abs_u" })
    await waitFor(() =>
      expect(within(chart).getByRole("img", { name: /max_abs_u over step: 2 points/ })).toBeVisible(),
    )
    // The bound of the contract is drawn with the data it applies to.
    expect(within(chart).getByText("above 1 stops the run")).toBeInTheDocument()
    const scalars = screen.getByRole("table", { name: "Quantities measured once" })
    const row = within(scalars).getByRole("row", { name: /max_rss/ })
    expect(row).toHaveTextContent("18366464")
    expect(row).toHaveTextContent("17.5 MiB")
    expect(row).toHaveTextContent("supervisor")
  })

  it("reports a run that does not exist", async () => {
    stubApi({ "/v1/workers": { workers: [], alive: 1 } })
    renderProjectView("runs/:runId", <RunView />, "/projects/prj_1/runs/run_404", {
      project: projectRecord(),
    })

    expect(await screen.findByText("Could not load the run")).toBeVisible()
  })
})
