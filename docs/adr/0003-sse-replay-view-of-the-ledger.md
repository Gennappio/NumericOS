# ADR-0003: Server-Sent Events as a replayable view of the ledger

- Status: accepted (M0-T05, 2026-10-12)
- Deciders: project owner, implementing agent
- Builds on: ADR-0002 (transactional event ledger, publish-after-commit)

## Context

Root `AGENTS.md`: the database plus the append-only ledger is the truth; "SSE is a view/replay
transport, not truth". `milestones/M0/AGENTS.md`: the SSE subscriber reads from the ledger and
replays by cursor / `Last-Event-ID`; a reconnect emits missed events once; clients de-duplicate
by event ID; no polling loop may fabricate progress. From M3 on, events will also be committed
by processes other than the API (the job supervisor), which cannot wake an in-process notifier.

## Decisions

1. **One route, two representations.** `GET /v1/events` answers a JSON page by default and a
   Server-Sent Events stream when the request accepts `text/event-stream`. Both read the same
   rows by the same cursor (`seq`) and serialise an event identically: the stream frame carries
   `id: <seq>` and the JSON event in `data`.
2. **Replay, then follow.** `events.stream.follow()` yields every event after the cursor in
   `seq` order, then waits. The notifier's flag is cleared before each ledger read, so a commit
   that lands during a read is not lost. A wait also ends after one heartbeat
   (`NUMERICOS_SSE_HEARTBEAT_SECONDS`, default 15), which bounds how late a subscriber learns of
   events committed by another process.
3. **Cursor rules.** The stream starts after `max(after, Last-Event-ID)`. In stream mode only
   `project_id` and `after` are accepted; `before`, `limit` and `order=desc` are a 422. An
   unknown project is a 404 and a cursor beyond the ledger head is a 409 `CURSOR_AHEAD`, both
   answered before the first byte: a cursor from another ledger must not turn into a stream that
   silently never delivers anything.
4. **Delivery semantics.** In-order and at-least-once for a client that resumes from the last
   `seq` it processed. A client that resumes from an older cursor sees events again and
   de-duplicates by `event_id`. No exactly-once claim is made.
5. **A library for the transport.** `sse-starlette` handles client disconnects, keep-alive
   comments and, most importantly, ending open streams promptly when the server is told to stop
   (so `--reload` and supervisors are not blocked by subscribers).
6. **The GUI treats the stream as a wake-up signal.** To connect, a project page reads the
   ledger head, subscribes right after it, and re-reads the project, board and recent events
   when the stream opens and on every event. On any error it closes the stream and repeats that
   sequence after 2 s; it does not use EventSource's own reconnect, so a cursor is never reused
   against a ledger that may have been replaced. While the stream is not live, the page polls
   every 5 s and says so.
7. **The CLI does not hide retries.** `numericos events follow` prints JSON Lines; when the
   stream breaks it reports the last `seq` it printed (`resume with --after N`) and exits 3.

## Consequences

- An idle subscriber costs one connection and one ledger read per heartbeat.
- One API process (`uvicorn --workers 1`) owns the wake-ups; other processes are covered by the
  heartbeat re-read, at up to one heartbeat of latency.
- Stream reads use the same `BEGIN IMMEDIATE` policy as every transaction (ADR-0002) and hold
  the write lock for the duration of one short read. Acceptable for a local single-user
  workbench; to be revisited with measured contention in M3.
- The list of projects has no stream yet and is polled every 5 s.
- Browsers allow six HTTP/1.1 connections per origin: more than six project pages open at once
  would queue. HTTP/2 or a shared stream is out of scope for M0.
