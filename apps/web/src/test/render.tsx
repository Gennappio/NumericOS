import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import type { ReactElement } from "react"
import { MemoryRouter } from "react-router"
import { vi } from "vitest"

/** Render with the providers the application installs in `main.tsx`. */
export function renderApp(ui: ReactElement, route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

export const HEALTH_OK = {
  status: "ok",
  app: "numericos",
  version: "0.0.1",
  time_utc: "2026-10-10T00:00:00Z",
  data_dir: "/tmp/numericos",
  db: "ok",
  schema_revision: "0001",
  expected_revision: "0001",
}

/**
 * Replace `fetch` with canned JSON bodies per API path; unknown paths answer 404. The object is
 * read on every call, so a test can change an answer after the page has loaded.
 */
export function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname
    const known = path in routes
    const body = known
      ? routes[path]
      : { error: { code: "NOT_FOUND", message: `no stub for ${path}`, details: {} } }
    return new Response(JSON.stringify(body), {
      status: known ? 200 : 404,
      headers: { "Content-Type": "application/json" },
    })
  })
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

export function stubUnreachableApi() {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))
}
