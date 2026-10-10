from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from numericos.core.enums import WorkflowStatus
from numericos.persistence.ordering import STEP, place
from numericos.persistence.unit_of_work import UnitOfWork
from tests import factories

UowFactory = Callable[[], UnitOfWork]


def test_project_round_trip_keeps_aware_utc_timestamps(uow: UowFactory) -> None:
    created_at = datetime(2026, 10, 10, 8, 30, 15, 123456, tzinfo=UTC)
    with uow() as unit:
        project = unit.projects.add(factories.project(created_at=created_at))
        unit.commit()

    with uow() as unit:
        loaded = unit.projects.get(project.id)

    assert loaded is not None
    assert loaded.created_at == created_at
    assert loaded.created_at.tzinfo is UTC


def test_naive_timestamps_are_rejected(uow: UowFactory) -> None:
    with pytest.raises(StatementError, match="naive"), uow() as unit:
        unit.projects.add(factories.project(created_at=datetime(2026, 10, 10)))


def test_projects_are_listed_in_creation_order(uow: UowFactory) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with uow() as unit:
        later = unit.projects.add(factories.project(name="later", created_at=base.replace(day=2)))
        earlier = unit.projects.add(factories.project(name="earlier", created_at=base))
        unit.commit()

    with uow() as unit:
        names = [project.name for project in unit.projects.list()]

    assert names == ["earlier", "later"]
    assert later.id != earlier.id


def test_cards_are_listed_by_column_then_rank(uow: UowFactory) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        unit.cards.add(
            factories.card(project.id, title="r1", workflow_status="review", sort_order=0)
        )
        unit.cards.add(
            factories.card(project.id, title="b2", workflow_status="backlog", sort_order=STEP)
        )
        unit.cards.add(
            factories.card(project.id, title="b1", workflow_status="backlog", sort_order=0)
        )
        unit.commit()

    with uow() as unit:
        titles = [card.title for card in unit.cards.list_for_project(project.id)]
        backlog = [card.title for card in unit.cards.list_column(project.id, "backlog")]

    assert titles == ["b1", "b2", "r1"]
    assert backlog == ["b1", "b2"]


def test_next_sort_order_appends_with_a_gap(uow: UowFactory) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        assert unit.cards.next_sort_order(project.id, "planned") == 0
        unit.cards.add(factories.card(project.id, workflow_status="planned", sort_order=0))
        assert unit.cards.next_sort_order(project.id, "planned") == STEP


def test_reindex_writes_only_changed_rows(uow: UowFactory) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        cards = [
            unit.cards.add(factories.card(project.id, title=title, sort_order=index * STEP))
            for index, title in enumerate(["a", "b", "c"])
        ]
        moved = cards[2]
        changed = unit.cards.reindex(cards, place([c.id for c in cards], moved.id, 0))
        unit.commit()

    assert changed == [(moved.id, 0), (cards[0].id, STEP), (cards[1].id, 2 * STEP)]
    with uow() as unit:
        titles = [card.title for card in unit.cards.list_column(project.id, "backlog")]
    assert titles == ["c", "a", "b"]


def test_foreign_keys_are_enforced(uow: UowFactory) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY"), uow() as unit:
        unit.cards.add(factories.card("prj_01J9W2Z4K7QX8YB3N5M6T0R1S2"))


def test_check_constraints_reject_unknown_vocabulary(uow: UowFactory) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        unit.commit()

    with pytest.raises(IntegrityError, match="CHECK"), uow() as unit:
        unit.cards.add(factories.card(project.id, type="wish"))

    with pytest.raises(IntegrityError, match="CHECK"), uow() as unit:
        unit.cards.add(factories.card(project.id, workflow_status="done"))

    assert WorkflowStatus.COMPLETED.value == "completed"  # the vocabulary has no "done"
