# ADR-0002: Transactional event ledger, publish-after-commit and column renumbering

- Status: accepted (M0-T02, 2026-10-10); the SSE transport on top of it is M0-T05
- Deciders: project owner, implementing agent

## Context

Root `AGENTS.md` makes the database plus an append-only event ledger the canonical workflow state
and demands that an event is published only after its commit; SSE is a view, not the truth.
`milestones/M0/AGENTS.md` requires the mutation and its event in the same transaction, cursor
ordering from a monotonic sequence (timestamps are display metadata) and a durable card ordering
computed by the backend.

## Decisions

1. **One table `events`, one cursor.** `seq INTEGER PRIMARY KEY AUTOINCREMENT` is the only
   ordering authority and the replay cursor; `event_id` (`evt_<ULID>`) is the client dedupe key.
   Every row carries `project_id`, `type`, `subject_id`, `actor`, `producer`, `severity`,
   `correlation_id`, `schema_version`, `payload` and `timestamp_utc`, as the root contract asks.
2. **Unit of work.** A mutation runs inside `UnitOfWork`: repositories change rows, `record()`
   inserts the event in the same session (so `seq` is assigned inside the transaction) and
   `commit()` performs exactly one COMMIT. Leaving the block without `commit()` discards
   everything; an exception rolls back state and event together.
3. **Publish only after commit.** `UnitOfWork.commit()` calls `EventNotifier.publish()` strictly
   after `session.commit()` returned. The notifier is a wake-up signal per project (an
   `asyncio.Event` per subscriber, set via `call_soon_threadsafe`), never a data channel:
   subscribers re-read the ledger by cursor, so nothing can be delivered before it is durable and
   a missed wake-up costs at most one heartbeat (T05).
4. **SQLite transaction policy.** pysqlite's implicit `BEGIN` is disabled and every transaction
   starts with `BEGIN IMMEDIATE`: writers are serialised up front, so a read-then-write
   transaction cannot fail with `SQLITE_BUSY_SNAPSHOT` and `busy_timeout` applies. WAL,
   `foreign_keys=ON` and `synchronous=FULL` are set on every connection.
5. **Column renumbering.** On every move the destination column is renumbered
   (`index * 1000`), using the pure function `place()`; only rows whose rank changes are written
   and siblings keep their `version`. One code path instead of midpoint insertion plus a rarely
   exercised renumbering fallback.
6. **Migrations only through Alembic**, with named constraints and `render_as_batch=True` so
   later `ALTER`s work on SQLite. Foreign-key enforcement is switched off before the migration
   transaction, verified with `foreign_key_check` afterwards and restored before the connection
   returns to the pool.

## Consequences

- Services (T03) never touch the session directly: they open a `UnitOfWork`, mutate through
  repositories, `record()` one event per successful request and `commit()`.
- A single API process (`uvicorn --workers 1`) owns the notifier; more workers would keep
  durability but lose live wake-ups. Documented as unsupported in M0.
- `alembic check` runs in the test suite: ORM models and migrations cannot drift silently.
