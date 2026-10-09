import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError, ApiUnreachableError, apiFetch } from "./client"

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("returns the parsed body and identifies the web surface", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { status: "ok" }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(apiFetch<{ status: string }>("/v1/health")).resolves.toEqual({ status: "ok" })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/v1\/health$/)
    expect(new Headers(init.headers).get("X-Actor")).toBe("web:local")
  })

  it("turns the error envelope into an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(404, {
          error: {
            code: "NOT_FOUND",
            message: "no such project",
            details: { id: "prj_x" },
            correlation_id: "cor_1",
          },
        }),
      ),
    )

    const error = await apiFetch("/v1/projects/prj_x").catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.status).toBe(404)
    expect(apiError.code).toBe("NOT_FOUND")
    expect(apiError.details).toEqual({ id: "prj_x" })
    expect(apiError.correlationId).toBe("cor_1")
  })

  it("falls back to HTTP_ERROR when the body is not an envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response("<html>502</html>", { status: 502, statusText: "Bad Gateway" })),
    )

    const error = await apiFetch("/v1/health").catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe("HTTP_ERROR")
    expect((error as ApiError).message).toBe("502 Bad Gateway")
  })

  it("reports an unreachable backend as a distinct error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))

    await expect(apiFetch("/v1/health")).rejects.toBeInstanceOf(ApiUnreachableError)
  })
})
