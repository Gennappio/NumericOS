from __future__ import annotations

from fastapi import APIRouter

from numericos.api.deps import Context, Uow
from numericos.api.errors import CONFLICT_RESPONSES
from numericos.core.schemas import CardOut, CardPatch
from numericos.services import cards

router = APIRouter(tags=["cards"])


@router.get("/cards/{card_id}", summary="Get one card")
def get_card(card_id: str, uow: Uow) -> CardOut:
    return cards.get_card(uow, card_id)


@router.patch(
    "/cards/{card_id}",
    summary="Edit and/or move a card (requires its current version)",
    responses=CONFLICT_RESPONSES,
)
def update_card(card_id: str, body: CardPatch, uow: Uow, context: Context) -> CardOut:
    return cards.update_card(uow, card_id, body, context)
