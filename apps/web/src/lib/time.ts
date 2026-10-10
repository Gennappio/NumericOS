/** Local display of a UTC timestamp from the API. Display only: ordering comes from the backend. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

export function formatClock(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString()
}
