import { useEffect, useRef, useState } from "react"
import { ApiError, type CursorStart } from "./client"

/** One reading of an append-only record of a run. */
export interface FeedPage<T> {
  items: T[]
  next_cursor: number
  has_more: boolean
  /** The run ended and everything was returned: nothing will ever follow. */
  complete: boolean
}

export interface Feed<T> {
  /** The newest items, oldest first; at most `keep` of them. */
  items: T[]
  /** How many older items were let go to stay within `keep`. */
  dropped: number
  complete: boolean
  /** True until the first reading has arrived. */
  loading: boolean
  /** Why the feed stopped, if a reading was refused. */
  error: unknown
}

interface FeedOptions {
  /** Begin with the last `tail` records instead of the first one. */
  tail?: number
  /** How many items to keep in memory. */
  keep: number
  /** Pause between readings once the end of what is recorded has been reached. */
  intervalMs: number
}

const EMPTY = { items: [], dropped: 0, complete: false, loading: true, error: undefined }

/**
 * Follows an append-only record (output lines, resource samples) by cursor: reads what exists,
 * then keeps asking for what was appended, until the server says nothing will follow.
 *
 * Each reading continues exactly where the previous one stopped, so nothing is read twice and
 * nothing is skipped. A component that should start over, for another run, is given another
 * `key` by its parent: the feed lives as long as the component.
 */
export function useCursorFeed<T>(
  read: (start: CursorStart) => Promise<FeedPage<T>>,
  { tail, keep, intervalMs }: FeedOptions,
): Feed<T> {
  const [feed, setFeed] = useState<Feed<T>>(EMPTY)
  const reader = useRef(read)
  useEffect(() => {
    reader.current = read
  }, [read])

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let cursor: number | undefined

    async function step() {
      try {
        const start: CursorStart =
          cursor !== undefined ? { after: cursor } : tail !== undefined ? { tail } : { after: 0 }
        const page = await reader.current(start)
        if (stopped) return
        cursor = page.next_cursor
        setFeed((previous) => {
          const items = [...previous.items, ...page.items]
          const excess = Math.max(0, items.length - keep)
          return {
            items: excess > 0 ? items.slice(excess) : items,
            dropped: previous.dropped + excess,
            complete: page.complete,
            loading: false,
            error: undefined,
          }
        })
        if (page.complete) return
        timer = setTimeout(() => void step(), page.has_more ? 0 : intervalMs)
      } catch (error) {
        if (stopped) return
        setFeed((previous) => ({ ...previous, loading: false, error }))
        // A typed answer (unknown run, refused cursor) will not change by asking again.
        if (error instanceof ApiError) return
        timer = setTimeout(() => void step(), intervalMs * 2)
      }
    }

    void step()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [tail, keep, intervalMs])

  return feed
}
