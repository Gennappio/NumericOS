import { afterEach, describe, expect, it, vi } from "vitest"
import { forgetPositions, readPositions, writePositions } from "./positions"

afterEach(() => {
  window.localStorage.clear()
  vi.restoreAllMocks()
})

const PLACES = { a: { x: 10, y: 20 }, b: { x: 480.5, y: -30 } }

describe("positions of the boxes of a board", () => {
  it("are remembered per pipeline and version", () => {
    writePositions("doc_1", 2, PLACES)

    expect(readPositions("doc_1", 2, ["a", "b"])).toEqual(PLACES)
    expect(readPositions("doc_1", 3, ["a", "b"])).toBeNull() // written again: another board
    expect(readPositions("doc_2", 2, ["a", "b"])).toBeNull()
  })

  it("count only when they are there for every box", () => {
    writePositions("doc_1", 1, PLACES)

    expect(readPositions("doc_1", 1, ["a", "b", "c"])).toBeNull()
    expect(readPositions("doc_1", 1, ["a"])).toEqual(PLACES)
  })

  it("of an earlier version are dropped when a newer one is remembered", () => {
    writePositions("doc_1", 1, PLACES)
    writePositions("doc_2", 1, PLACES)
    writePositions("doc_1", 2, PLACES)

    expect(readPositions("doc_1", 1, ["a", "b"])).toBeNull()
    expect(readPositions("doc_1", 2, ["a", "b"])).toEqual(PLACES)
    expect(readPositions("doc_2", 1, ["a", "b"])).toEqual(PLACES) // another pipeline's stay
  })

  it("are forgotten on request", () => {
    writePositions("doc_1", 2, PLACES)
    writePositions("doc_2", 1, PLACES)
    forgetPositions("doc_1")

    expect(readPositions("doc_1", 2, ["a", "b"])).toBeNull()
    expect(readPositions("doc_2", 1, ["a", "b"])).toEqual(PLACES)
  })

  it("are no positions when what is kept is not ours, or the browser keeps nothing", () => {
    window.localStorage.setItem("numericos:pipeline:doc_1:1", "{not json")
    expect(readPositions("doc_1", 1, ["a"])).toBeNull()
    window.localStorage.setItem("numericos:pipeline:doc_1:1", JSON.stringify({ a: { x: "left" } }))
    expect(readPositions("doc_1", 1, ["a"])).toBeNull()

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("The quota has been exceeded.", "QuotaExceededError")
    })
    expect(() => writePositions("doc_1", 1, PLACES)).not.toThrow()
  })
})
