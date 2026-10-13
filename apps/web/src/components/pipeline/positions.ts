import type { Positions } from "@/components/pipeline/layout"

/**
 * Where the researcher put the boxes of a board, remembered by this browser. It is how one
 * person looks at the board, not a fact about the project: it is not sent to the API. A
 * pipeline that was written again is another board, and is laid out afresh.
 */

const PREFIX = "numericos:pipeline:"
const key = (documentId: string, version: number) => `${PREFIX}${documentId}:${version}`

/** The remembered positions, if they are there for every one of the boxes. */
export function readPositions(documentId: string, version: number, ids: string[]): Positions | null {
  try {
    const stored = JSON.parse(window.localStorage.getItem(key(documentId, version)) ?? "null") as
      | Positions
      | null
    const complete =
      stored !== null &&
      ids.every((id) => Number.isFinite(stored[id]?.x) && Number.isFinite(stored[id]?.y))
    return complete ? stored : null
  } catch {
    // A browser may refuse its storage, and what is kept there may not be ours.
    return null
  }
}

export function writePositions(documentId: string, version: number, positions: Positions): void {
  try {
    forget(documentId)
    window.localStorage.setItem(key(documentId, version), JSON.stringify(positions))
  } catch {
    // Not remembered: the board is laid out by itself the next time.
  }
}

/** Forget what was remembered of every version of a pipeline. */
export function forgetPositions(documentId: string): void {
  try {
    forget(documentId)
  } catch {
    // Nothing to forget in a browser that keeps nothing.
  }
}

function forget(documentId: string): void {
  const storage = window.localStorage
  const ours = Array.from({ length: storage.length }, (_, index) => storage.key(index)).filter(
    (name): name is string => name !== null && name.startsWith(`${PREFIX}${documentId}:`),
  )
  for (const name of ours) storage.removeItem(name)
}
