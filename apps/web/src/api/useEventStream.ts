import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { ApiError, eventStreamUrl, type EventOut } from "./client"
import { queryKeys, recentEventsQuery } from "./queries"

/** `live`: every change arrives as an event. Otherwise the page falls back to polling. */
export type Transport = "connecting" | "live" | "reconnecting"

export const RECONNECT_MS = 2_000
const REMEMBERED_EVENT_IDS = 500

/**
 * Keeps a project page current through the project's event stream.
 *
 * The stream is a wake-up signal, not a second source of state: every event (and every
 * successful connection) makes the page re-read the project, its board and its recent events
 * from the API. To connect, the hook first reads the ledger head and then subscribes right
 * after it, so nothing committed between that read and the subscription can be missed, and a
 * cursor from an earlier connection is never reused against a ledger that may have changed.
 */
export function useEventStream(projectId: string): Transport {
  const queryClient = useQueryClient()
  const [transport, setTransport] = useState<Transport>("connecting")

  useEffect(() => {
    let source: EventSource | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const seen = new Set<string>()

    const refresh = () =>
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })

    async function connect() {
      let cursor: number
      try {
        const page = await queryClient.fetchQuery({
          ...recentEventsQuery(projectId),
          staleTime: 0,
        })
        cursor = page.events[0]?.seq ?? 0
      } catch (error) {
        // A typed answer (unknown project, ...) will not change by asking again.
        if (!(error instanceof ApiError)) reconnect()
        return
      }
      if (stopped) return

      source = new EventSource(eventStreamUrl(projectId, cursor))
      source.onopen = () => {
        setTransport("live")
        refresh() // state read before the subscription may predate the cursor's last events
      }
      source.onmessage = (message: MessageEvent<string>) => {
        const event = JSON.parse(message.data) as EventOut
        if (seen.has(event.event_id)) return
        seen.add(event.event_id)
        if (seen.size > REMEMBERED_EVENT_IDS) seen.delete(seen.values().next().value!)
        refresh()
      }
      source.onerror = reconnect
    }

    function reconnect() {
      source?.close()
      source = undefined
      if (stopped) return
      setTransport("reconnecting")
      retry = setTimeout(() => void connect(), RECONNECT_MS)
    }

    void connect()
    return () => {
      stopped = true
      source?.close()
      clearTimeout(retry)
    }
  }, [projectId, queryClient])

  return transport
}
