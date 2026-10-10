"""Durable card ordering inside a board column.

On every move the destination column is renumbered (``index * STEP``): one code path, a
deterministic result and a ``position`` that maps 1:1 to the index the user sees. Columns hold
tens of cards, so the extra UPDATEs are negligible inside one serialised transaction.
"""

from __future__ import annotations

from collections.abc import Sequence

STEP = 1000


def place(ordered_ids: Sequence[str], moving_id: str, position: int | None) -> list[str]:
    """Return the column order with ``moving_id`` at ``position`` (clamped; ``None`` appends)."""
    ids = [card_id for card_id in ordered_ids if card_id != moving_id]
    index = len(ids) if position is None else max(0, min(position, len(ids)))
    ids.insert(index, moving_id)
    return ids


def ranks(ordered_ids: Sequence[str]) -> dict[str, int]:
    return {card_id: index * STEP for index, card_id in enumerate(ordered_ids)}
