"""Request-scoped dependencies: a unit of work and the event context of the caller."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from numericos.events.ledger import EventContext
from numericos.persistence.unit_of_work import UnitOfWork

#: ``<surface>:<name>``, e.g. ``web:local``, ``cli:local``, ``cli:seed``. Recorded, not trusted.
ACTOR_PATTERN = r"^[a-z][a-z0-9_-]{0,19}:[A-Za-z0-9_.:-]{1,99}$"
DEFAULT_ACTOR = "api:unknown"


def get_uow(request: Request) -> UnitOfWork:
    state = request.app.state
    return UnitOfWork(state.session_factory, state.notifier)


def get_event_context(
    request: Request,
    x_actor: Annotated[
        str,
        Header(
            pattern=ACTOR_PATTERN,
            description="Label of the calling surface, stored on every event it causes.",
        ),
    ] = DEFAULT_ACTOR,
) -> EventContext:
    return EventContext(actor=x_actor, correlation_id=request.state.correlation_id)


Uow = Annotated[UnitOfWork, Depends(get_uow)]
Context = Annotated[EventContext, Depends(get_event_context)]
