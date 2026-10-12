import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { defineConfig, devices } from "@playwright/test"
import { API_PORT, API_URL, WEB_PORT, WEB_URL } from "./e2e/urls"

// The coding agent of the browser tests is the stand-in for Claude Code of the Python tests:
// same flags, same records, no model and no cost.
const FAKE_CLAUDE = JSON.stringify([
  resolve("../../.venv/bin/python"),
  resolve("../../tests/fake_claude.py"),
])

/**
 * Browser tests run against a REAL API process and a REAL supervisor process on a throwaway
 * data directory, and the Vite dev server; nothing is mocked except where a test deliberately
 * cuts the network. Runs execute real programs.
 *
 * One worker, files in alphabetical order: `00-first-run.spec.ts` must see the empty database
 * that every `playwright test` invocation starts with.
 */
// The API and the supervisor share one data directory. The variable keeps it the same in the
// processes that load this file again.
process.env.NUMERICOS_E2E_DATA_DIR ??= mkdtempSync(join(tmpdir(), "numericos-e2e-"))
const DATA_DIR = process.env.NUMERICOS_E2E_DATA_DIR
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  // The GUI learns about changes made elsewhere by polling every 5 s (until the SSE stream).
  expect: { timeout: 10_000 },
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run numericos serve --port ${API_PORT} --data-dir ${DATA_DIR}`,
      cwd: "../..",
      url: `${API_URL}/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        UV_PROJECT_ENVIRONMENT: ".venv",
        NUMERICOS_CORS_ORIGINS: JSON.stringify([WEB_URL]),
        NUMERICOS_CLAUDE_COMMAND: FAKE_CLAUDE,
      },
    },
    {
      // Started after the API, which has migrated the database by then.
      command: `uv run numericos worker run --data-dir ${DATA_DIR} --poll-interval 0.2`,
      cwd: "../..",
      wait: { stderr: /supervisor \S+ serving/ },
      reuseExistingServer: false,
      timeout: 60_000,
      env: { UV_PROJECT_ENVIRONMENT: ".venv", NUMERICOS_CLAUDE_COMMAND: FAKE_CLAUDE },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      url: WEB_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_URL: API_URL },
    },
  ],
})
