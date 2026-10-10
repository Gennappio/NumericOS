"""Read access to the event ledger. ``seq`` is the cursor; timestamps never order anything."""

from __future__ import annotations

from numericos.core.schemas import EventOut, EventPage
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import require_project


def list_events(
    uow: UnitOfWork,
    project_id: str,
    *,
    after: int | None = None,
    before: int | None = None,
    limit: int = 100,
    descending: bool = False,
) -> EventPage:
    """One page of a project's ledger.

    ``next_cursor`` is the ``seq`` of the last returned event: pass it as ``after`` (ascending)
    or ``before`` (descending) to continue. It is null for an empty page.
    """
    with uow:
        require_project(uow, project_id)
        rows = uow.events.page(
            project_id, after=after, before=before, limit=limit + 1, descending=descending
        )
        events = [EventOut.model_validate(row) for row in rows[:limit]]
        return EventPage(
            events=events,
            next_cursor=events[-1].seq if events else None,
            has_more=len(rows) > limit,
        )
