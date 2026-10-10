"""Board card use cases, including durable placement inside a workflow column.

Workflow status is operational. Nothing here derives or stores scientific validity: a card in
``completed`` is finished work, not a supported hypothesis.
"""

from __future__ import annotations

from typing import Any

from numericos.core.enums import WORKFLOW_ORDER, EventType
from numericos.core.errors import ProjectMismatchError
from numericos.core.ids import new_id
from numericos.core.schemas import BoardOut, CardCreate, CardOut, CardPatch
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import BoardCard
from numericos.persistence.ordering import place
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.services.guards import check_version, require_card, require_project

#: Content fields a PATCH may change, in the order they are reported in ``changed_fields``.
#: Placement (``workflow_status``, ``position``) is handled separately.
PATCHABLE = ("type", "title", "description", "entity_ref")


def create_card(
    uow: UnitOfWork, project_id: str, data: CardCreate, context: EventContext
) -> CardOut:
    """Create a card at the end of its column."""
    now = utcnow()
    with uow:
        project = require_project(uow, project_id)
        status = data.workflow_status.value
        card = uow.cards.add(
            BoardCard(
                id=new_id("card"),
                project_id=project.id,
                type=data.type.value,
                title=data.title,
                description=data.description,
                workflow_status=status,
                sort_order=uow.cards.next_sort_order(project.id, status),
                entity_ref=data.entity_ref,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        out = CardOut.model_validate(card)
        uow.record(
            build_event(
                event_type=EventType.CARD_CREATED,
                project_id=project.id,
                subject_id=card.id,
                payload={"card": out.model_dump(mode="json")},
                context=context,
            )
        )
        uow.commit()
    return out


def get_card(uow: UnitOfWork, card_id: str) -> CardOut:
    with uow:
        return CardOut.model_validate(require_card(uow, card_id))


def get_board(uow: UnitOfWork, project_id: str) -> BoardOut:
    with uow:
        project = require_project(uow, project_id)
        return BoardOut(
            project_id=project.id,
            workflow_statuses=list(WORKFLOW_ORDER),
            cards=[CardOut.model_validate(card) for card in uow.cards.list_for_project(project.id)],
        )


def update_card(uow: UnitOfWork, card_id: str, patch: CardPatch, context: EventContext) -> CardOut:
    """Edit and/or move a card.

    Placement: a new ``workflow_status`` moves the card to ``position`` in that column (append
    when omitted); ``position`` alone reorders inside the current column. The destination column
    is renumbered; siblings keep their ``version`` because their placement is derived, not edited.
    """
    with uow:
        card = require_card(uow, card_id)
        if patch.project_id is not None and patch.project_id != card.project_id:
            raise ProjectMismatchError(
                f"card {card.id} does not belong to project {patch.project_id}",
                details={
                    "card_id": card.id,
                    "card_project_id": card.project_id,
                    "requested_project_id": patch.project_id,
                },
            )
        check_version("card", card.id, current=card.version, provided=patch.version)

        values = patch.model_dump(mode="json", include=set(PATCHABLE) & patch.model_fields_set)
        changed = [
            field
            for field in PATCHABLE
            if field in values and getattr(card, field) != values[field]
        ]

        origin = {"workflow_status": card.workflow_status, "sort_order": card.sort_order}
        target_status = (
            patch.workflow_status.value
            if patch.workflow_status is not None
            else card.workflow_status
        )
        moved = False
        reindexed: list[tuple[str, int]] = []
        if target_status != card.workflow_status:
            column = uow.cards.list_column(card.project_id, target_status)
            order = place([other.id for other in column], card.id, patch.position)
            card.workflow_status = target_status
            reindexed = uow.cards.reindex([*column, card], order)
            moved = True
        elif patch.position is not None:
            column = uow.cards.list_column(card.project_id, target_status)
            current = [other.id for other in column]
            order = place(current, card.id, patch.position)
            if order != current:
                reindexed = uow.cards.reindex(column, order)
                moved = True

        if not changed and not moved:
            return CardOut.model_validate(card)

        for field in changed:
            setattr(card, field, values[field])
        card.version += 1
        card.updated_at = utcnow()
        out = CardOut.model_validate(card)

        payload: dict[str, Any] = {"card": out.model_dump(mode="json"), "changed_fields": changed}
        if moved:
            payload["from"] = origin
            payload["to"] = {"workflow_status": card.workflow_status, "sort_order": card.sort_order}
            payload["reindexed"] = [
                {"id": sibling_id, "sort_order": rank}
                for sibling_id, rank in reindexed
                if sibling_id != card.id
            ]
        uow.record(
            build_event(
                event_type=EventType.CARD_MOVED if moved else EventType.CARD_UPDATED,
                project_id=card.project_id,
                subject_id=card.id,
                payload=payload,
                context=context,
            )
        )
        uow.commit()
    return out
