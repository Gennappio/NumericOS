/** Local display of a UTC timestamp from the API. Display only: ordering comes from the backend. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

/** With seconds: events of one burst must stay distinguishable. */
export function formatEventTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" })
}

export function formatClock(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString()
}
