"""The event ledger over HTTP: one JSON page, or a replayable Server-Sent Events stream.

Both representations of the same route read the same ledger by the same cursor (``seq``). The
stream is a view of durable rows: it replays everything after the cursor, then follows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from numericos.api.deps import Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.errors import CursorAheadError, InvalidRequestError
from numericos.core.schemas import EventPage
from numericos.events.stream import follow
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services import events

router = APIRouter(tags=["events"])

DEFAULT_PAGE_SIZE = 100
STREAM_PAGE_SIZE = 500
#: Delay EventSource clients wait before reconnecting on their own.
CLIENT_RETRY_MS = 2000
SEND_TIMEOUT_SECONDS = 30.0

EVENT_STREAM = "text/event-stream"

RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "A page of events as JSON. With `Accept: text/event-stream` the response is a "
            "Server-Sent Events stream instead: it replays every event after the cursor in "
            "`seq` order, then follows the ledger. Each frame has `id: <seq>` and the event "
            "as JSON in `data`; reconnecting with `Last-Event-ID` resumes after that event."
        ),
        "content": {EVENT_STREAM: {"schema": {"type": "string"}}},
    },
    **CONFLICT_RESPONSES,
}


@router.get(
    "/events",
    summary="Read a project's event ledger by cursor (JSON page or SSE stream)",
    response_model=EventPage,
    responses=RESPONSES,
)
def list_events(
    request: Request,
    uow: Uow,
    project_id: Annotated[str, Query(description="Project whose ledger is read.")],
    after: Annotated[
        int | None, Query(ge=0, description="Cursor: only events with seq greater than this.")
    ] = None,
    before: Annotated[
        int | None, Query(ge=1, description="Only events with seq lower than this. JSON only.")
    ] = None,
    limit: Annotated[
        int | None, Query(ge=1, le=1000, description="Page size, default 100. JSON only.")
    ] = None,
    order: Annotated[
        Literal["asc", "desc"], Query(description="Ordering by seq. A stream is always asc.")
    ] = "asc",
    run_id: Annotated[
        str | None, Query(description="Only events correlated with this run. JSON only.")
    ] = None,
    last_event_id: Annotated[
        str | None,
        Header(
            pattern=r"^\d{1,18}$",
            description="Sent by EventSource clients when they reconnect to a stream.",
        ),
    ] = None,
) -> Any:
    if EVENT_STREAM not in request.headers.get("accept", ""):
        return events.list_events(
            uow,
            project_id,
            after=after,
            before=before,
            limit=limit or DEFAULT_PAGE_SIZE,
            descending=order == "desc",
            run_id=run_id,
        )

    unsupported = [
        name
        for name, given in (
            ("before", before is not None),
            ("limit", limit is not None),
            ("order", order != "asc"),
            ("run_id", run_id is not None),
        )
        if given
    ]
    if unsupported:
        raise InvalidRequestError(
            "an event stream only takes project_id and after",
            details={
                "errors": [
                    {
                        "loc": ["query", name],
                        "msg": "not supported by the event stream",
                        "type": "stream_unsupported",
                    }
                    for name in unsupported
                ]
            },
        )

    cursor = max(after or 0, int(last_event_id or 0))
    # Checked before the first byte is streamed: an unknown project is a 404, and a cursor
    # beyond the head cannot come from this ledger (it would silently never deliver anything).
    head = events.ledger_head(uow, project_id)
    if cursor > head:
        raise CursorAheadError(
            f"cursor {cursor} is ahead of the ledger head {head}: read the current state again",
            details={"cursor": cursor, "ledger_head": head},
        )

    state = request.app.state
    heartbeat: float = state.settings.sse_heartbeat_seconds

    async def read_after(seq: int) -> EventPage:
        return await run_in_threadpool(
            events.list_events,
            UnitOfWork(state.session_factory, state.notifier),
            project_id,
            after=seq,
            limit=STREAM_PAGE_SIZE,
        )

    async def frames() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent(retry=CLIENT_RETRY_MS)
        ledger = follow(state.notifier, project_id, read_after, cursor, heartbeat=heartbeat)
        async with aclosing(ledger) as stream:  # closing the response unsubscribes at once
            async for event in stream:
                yield ServerSentEvent(id=str(event.seq), data=event.model_dump_json())

    return EventSourceResponse(frames(), ping=heartbeat, send_timeout=SEND_TIMEOUT_SECONDS)
