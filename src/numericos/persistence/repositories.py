"""Thin query/persistence helpers over one Session. Business rules live in services."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from numericos.core.enums import WORKFLOW_ORDER
from numericos.persistence.models import BoardCard, Event, Project
from numericos.persistence.ordering import STEP, ranks


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, project: Project) -> Project:
        self._session.add(project)
        self._session.flush()
        return project

    def get(self, project_id: str) -> Project | None:
        return self._session.get(Project, project_id)

    def list(self) -> list[Project]:
        statement = select(Project).order_by(Project.created_at, Project.id)
        return list(self._session.scalars(statement))


class CardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, card: BoardCard) -> BoardCard:
        self._session.add(card)
        self._session.flush()
        return card

    def get(self, card_id: str) -> BoardCard | None:
        return self._session.get(BoardCard, card_id)

    def list_for_project(self, project_id: str) -> list[BoardCard]:
        """All cards of a project in board order: column order, then sort_order, then id."""
        statement = (
            select(BoardCard)
            .where(BoardCard.project_id == project_id)
            .order_by(BoardCard.sort_order, BoardCard.id)
        )
        cards = list(self._session.scalars(statement))
        column_rank = {status.value: index for index, status in enumerate(WORKFLOW_ORDER)}
        cards.sort(key=lambda card: column_rank[card.workflow_status])  # stable sort
        return cards

    def list_column(self, project_id: str, workflow_status: str) -> list[BoardCard]:
        statement = (
            select(BoardCard)
            .where(BoardCard.project_id == project_id)
            .where(BoardCard.workflow_status == workflow_status)
            .order_by(BoardCard.sort_order, BoardCard.id)
        )
        return list(self._session.scalars(statement))

    def next_sort_order(self, project_id: str, workflow_status: str) -> int:
        statement = (
            select(func.max(BoardCard.sort_order))
            .where(BoardCard.project_id == project_id)
            .where(BoardCard.workflow_status == workflow_status)
        )
        current = self._session.scalar(statement)
        return 0 if current is None else current + STEP

    def reindex(
        self, cards: Sequence[BoardCard], ordered_ids: Sequence[str]
    ) -> list[tuple[str, int]]:
        """Assign ranks following ``ordered_ids``; only rows whose rank changes are written."""
        by_id = {card.id: card for card in cards}
        changed: list[tuple[str, int]] = []
        for card_id, rank in ranks(ordered_ids).items():
            card = by_id[card_id]
            if card.sort_order != rank:
                card.sort_order = rank
                changed.append((card_id, rank))
        self._session.flush()
        return changed


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: Event) -> Event:
        """Insert the row now so that ``seq`` is assigned inside the caller's transaction."""
        self._session.add(event)
        self._session.flush()
        return event

    def page(
        self,
        project_id: str,
        *,
        after: int | None = None,
        before: int | None = None,
        limit: int = 100,
        descending: bool = False,
    ) -> list[Event]:
        statement = select(Event).where(Event.project_id == project_id)
        if after is not None:
            statement = statement.where(Event.seq > after)
        if before is not None:
            statement = statement.where(Event.seq < before)
        order = Event.seq.desc() if descending else Event.seq.asc()
        return list(self._session.scalars(statement.order_by(order).limit(limit)))

    def count(self, project_id: str) -> int:
        statement = select(func.count()).select_from(Event).where(Event.project_id == project_id)
        return self._session.scalar(statement) or 0
