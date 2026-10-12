import { renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ApiError, type CursorStart } from "./client"
import { useCursorFeed, type FeedPage } from "./useCursorFeed"

/** A record that grows: readings return what is there after the cursor, `limit` at a time. */
function record(limit: number) {
  const items: number[] = []
  let ended = false
  const starts: CursorStart[] = []
  const read = vi.fn(async (start: CursorStart): Promise<FeedPage<number>> => {
    starts.push(start)
    const from = "after" in start ? start.after : Math.max(0, items.length - start.tail)
    const page = items.slice(from, from + limit)
    const next = from + page.length
    return {
      items: page,
      next_cursor: next,
      has_more: next < items.length,
      complete: ended && next >= items.length,
    }
  })
  return {
    read,
    starts,
    append: (...values: number[]) => items.push(...values),
    end: () => {
      ended = true
    },
  }
}

const OPTIONS = { keep: 100, intervalMs: 5 }

describe("useCursorFeed", () => {
  it("reads what exists page by page, then what is appended, and stops at the end", async () => {
    const source = record(2)
    source.append(1, 2, 3, 4, 5)
    const { result } = renderHook(() => useCursorFeed(source.read, OPTIONS))

    await waitFor(() => expect(result.current.items).toEqual([1, 2, 3, 4, 5]))
    expect(result.current.complete).toBe(false)

    source.append(6, 7)
    await waitFor(() => expect(result.current.items).toEqual([1, 2, 3, 4, 5, 6, 7]))

    source.end()
    await waitFor(() => expect(result.current.complete).toBe(true))
    const calls = source.read.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(source.read.mock.calls.length).toBe(calls) // nothing will follow: no more requests
    expect(source.starts[0]).toEqual({ after: 0 })
    expect(source.starts[1]).toEqual({ after: 2 }) // exactly where the first page stopped
  })

  it("can begin with the last records only", async () => {
    const source = record(50)
    source.append(...Array.from({ length: 20 }, (_, index) => index))
    source.end()
    const { result } = renderHook(() => useCursorFeed(source.read, { ...OPTIONS, tail: 3 }))

    await waitFor(() => expect(result.current.complete).toBe(true))
    expect(result.current.items).toEqual([17, 18, 19])
    expect(source.starts[0]).toEqual({ tail: 3 })
  })

  it("keeps the newest items and says how many older ones it let go", async () => {
    const source = record(4)
    source.append(...Array.from({ length: 10 }, (_, index) => index))
    source.end()
    const { result } = renderHook(() => useCursorFeed(source.read, { keep: 6, intervalMs: 5 }))

    await waitFor(() => expect(result.current.complete).toBe(true))
    expect(result.current.items).toEqual([4, 5, 6, 7, 8, 9])
    expect(result.current.dropped).toBe(4)
  })

  it("stops on an answer that asking again cannot change, and reports it", async () => {
    const refused = new ApiError(404, { code: "NOT_FOUND", message: "run not found", details: {} })
    const read = vi.fn().mockRejectedValue(refused)
    const { result } = renderHook(() => useCursorFeed<number>(read, OPTIONS))

    await waitFor(() => expect(result.current.error).toBe(refused))
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(read).toHaveBeenCalledTimes(1)
    expect(result.current.loading).toBe(false)
  })

  it("keeps trying when the backend is briefly unreachable", async () => {
    const source = record(10)
    source.append(1)
    source.end()
    const read = vi
      .fn<(start: CursorStart) => Promise<FeedPage<number>>>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockImplementation(source.read)
    const { result } = renderHook(() => useCursorFeed(read, OPTIONS))

    await waitFor(() => expect(result.current.items).toEqual([1]))
    expect(result.current.error).toBeUndefined()
  })
})
