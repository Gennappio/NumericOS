from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from numericos.api.deps import Uow
from numericos.core.schemas import EventPage
from numericos.services import events

router = APIRouter(tags=["events"])


@router.get("/events", summary="Read a project's event ledger by cursor")
def list_events(
    uow: Uow,
    project_id: Annotated[str, Query(description="Project whose ledger is read.")],
    after: Annotated[
        int | None, Query(ge=0, description="Return events with seq greater than this cursor.")
    ] = None,
    before: Annotated[
        int | None, Query(ge=1, description="Return events with seq lower than this value.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    order: Annotated[Literal["asc", "desc"], Query(description="Ordering by seq.")] = "asc",
) -> EventPage:
    return events.list_events(
        uow, project_id, after=after, before=before, limit=limit, descending=order == "desc"
    )
