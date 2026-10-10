import { defineConfig, devices } from "@playwright/test"
import { API_PORT, API_URL, WEB_PORT, WEB_URL } from "./e2e/urls"

/**
 * Browser tests run against a REAL API process on a throwaway data directory and the Vite dev
 * server; nothing is mocked except where a test deliberately cuts the network.
 *
 * One worker, files in alphabetical order: `00-first-run.spec.ts` must see the empty database
 * that every `playwright test` invocation starts with.
 */
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
      command: `uv run numericos serve --ephemeral --port ${API_PORT}`,
      cwd: "../..",
      url: `${API_URL}/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        UV_PROJECT_ENVIRONMENT: ".venv",
        NUMERICOS_CORS_ORIGINS: JSON.stringify([WEB_URL]),
      },
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
