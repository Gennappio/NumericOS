import type { EventOut, EventPage } from "@/api/client"

/** A ledger entry as the API returns it; override what a test cares about. */
export function ledgerEvent(seq: number, overrides: Partial<EventOut> = {}): EventOut {
  return {
    event_id: `evt_${seq}`,
    seq,
    project_id: "prj_1",
    type: "CARD_CREATED",
    subject_id: "card_1",
    actor: "web:local",
    producer: "api",
    severity: "info",
    correlation_id: `cor_${seq}`,
    schema_version: 1,
    timestamp_utc: "2026-10-12T10:00:00Z",
    payload: { card: { title: `Card ${seq}`, workflow_status: "backlog" } },
    ...overrides,
  }
}

/** A page of the newest entries, newest first, as `order=desc` returns them. */
export function newestFirst(...seqs: number[]): EventPage {
  return { events: seqs.map((seq) => ledgerEvent(seq)), next_cursor: seqs.at(-1) ?? null, has_more: false }
}
