import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ledgerEvent, newestFirst } from "@/test/events"
import { stubApi, stubUnreachableApi } from "@/test/render"
import { RECONNECT_MS, useEventStream } from "./useEventStream"

const PROJECT = "prj_1"
const PROJECT_DATA = { queryKey: ["projects", PROJECT] }

/** Stands in for the browser's EventSource; tests drive its callbacks by hand. */
class FakeEventSource {
  static opened: FakeEventSource[] = []
  url: string
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeEventSource.opened.push(this)
  }

  close() {
    this.closed = true
  }
}

function Probe() {
  return <output>{useEventStream(PROJECT)}</output>
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const view = render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  )
  return { invalidate, view }
}

const transport = () => screen.getByRole("status").textContent
const stream = (index: number) => FakeEventSource.opened[index]
const streams = () => FakeEventSource.opened.length
const untilStreams = (count: number, timeout = 1000) =>
  vi.waitFor(() => expect(streams()).toBe(count), { timeout })
const receive = (source: FakeEventSource, seq: number) =>
  act(() => source.onmessage?.({ data: JSON.stringify(ledgerEvent(seq)) }))

describe("useEventStream", () => {
  beforeEach(() => {
    FakeEventSource.opened = []
    vi.stubGlobal("EventSource", FakeEventSource)
  })
  afterEach(() => vi.unstubAllGlobals())

  it("reads the ledger head, then subscribes right after it", async () => {
    stubApi({ "/v1/events": newestFirst(9, 7, 3) })

    const { invalidate } = mount()
    expect(transport()).toBe("connecting")
    await untilStreams(1)

    expect(stream(0).url).toMatch(/\/v1\/events\?project_id=prj_1&after=9$/)
    act(() => stream(0).onopen?.())
    expect(transport()).toBe("live")
    // State read before the subscription is re-read once the stream is open.
    expect(invalidate).toHaveBeenCalledWith(PROJECT_DATA)
  })

  it("subscribes from the start of an empty ledger", async () => {
    stubApi({ "/v1/events": newestFirst() })

    mount()
    await untilStreams(1)

    expect(stream(0).url).toMatch(/&after=0$/)
  })

  it("re-reads the project once for every new event", async () => {
    stubApi({ "/v1/events": newestFirst(9) })
    const { invalidate } = mount()
    await untilStreams(1)
    act(() => stream(0).onopen?.())
    invalidate.mockClear()

    receive(stream(0), 10)
    receive(stream(0), 10) // delivered twice: the event ID is already known
    receive(stream(0), 11)

    expect(invalidate.mock.calls).toEqual([[PROJECT_DATA], [PROJECT_DATA]])
  })

  it("closes a broken stream, says so and reopens it from a freshly read head", async () => {
    const routes = { "/v1/events": newestFirst(9) }
    stubApi(routes)
    mount()
    await untilStreams(1)
    act(() => stream(0).onopen?.())

    routes["/v1/events"] = newestFirst(12, 9) // the ledger moved on while disconnected
    act(() => stream(0).onerror?.())

    expect(stream(0).closed).toBe(true)
    expect(transport()).toBe("reconnecting")
    await untilStreams(2, RECONNECT_MS + 2000)
    expect(stream(1).url).toMatch(/&after=12$/)
    act(() => stream(1).onopen?.())
    expect(transport()).toBe("live")
  })

  it("keeps trying while the backend is unreachable", async () => {
    stubUnreachableApi()

    mount()

    await vi.waitFor(() => expect(transport()).toBe("reconnecting"))
    expect(streams()).toBe(0)
  })

  it("does not ask again when the API gives a typed answer such as an unknown project", async () => {
    const fetchMock = stubApi({}) // every path answers 404 NOT_FOUND

    mount()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, RECONNECT_MS + 300))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(streams()).toBe(0)
  })

  it("closes the stream when the page goes away", async () => {
    stubApi({ "/v1/events": newestFirst(9) })
    const { view } = mount()
    await untilStreams(1)

    view.unmount()

    expect(stream(0).closed).toBe(true)
  })
})
