from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from numericos.events.notifier import EventNotifier
from numericos.persistence import migrate
from numericos.persistence.engine import make_engine, make_session_factory
from numericos.persistence.unit_of_work import UnitOfWork
from tests import factories

UowFactory = Callable[[], UnitOfWork]


def _counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as connection:
        projects = connection.execute(text("SELECT count(*) FROM projects")).scalar_one()
        cards = connection.execute(text("SELECT count(*) FROM board_cards")).scalar_one()
        events = connection.execute(text("SELECT count(*) FROM events")).scalar_one()
    return projects, cards, events


def test_commit_persists_state_and_event_together(uow: UowFactory, engine: Engine) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        event = unit.record(factories.event(project.id, project.id))
        assert event.seq == 1  # assigned inside the transaction
        unit.commit()

    assert _counts(engine) == (1, 0, 1)
    with uow() as unit:
        stored = unit.events.page(project.id)
    assert [e.event_id for e in stored] == [event.event_id]
    assert stored[0].timestamp_utc.tzinfo is not None


def test_failure_rolls_back_state_and_event(uow: UowFactory, engine: Engine) -> None:
    with pytest.raises(IntegrityError), uow() as unit:
        project = unit.projects.add(factories.project())
        unit.record(factories.event(project.id, project.id))
        unit.cards.add(factories.card(project.id, type="not-a-type"))  # CHECK fails at flush

    assert _counts(engine) == (0, 0, 0)


def test_leaving_without_commit_discards_everything(uow: UowFactory, engine: Engine) -> None:
    with uow() as unit:
        project = unit.projects.add(factories.project())
        unit.record(factories.event(project.id, project.id))

    assert _counts(engine) == (0, 0, 0)


def test_publish_happens_only_after_a_durable_commit(
    session_factory: sessionmaker[Session], engine: Engine
) -> None:
    seen: list[tuple[str, int, bool]] = []

    class Spy(EventNotifier):
        def publish(self, project_id: str, seq: int) -> None:
            with engine.connect() as fresh:  # a different connection must already see the row
                visible = fresh.execute(
                    text("SELECT count(*) FROM events WHERE seq = :seq"), {"seq": seq}
                ).scalar_one()
            seen.append((project_id, seq, visible == 1))

    with UnitOfWork(session_factory, Spy()) as unit:
        project = unit.projects.add(factories.project())
        unit.record(factories.event(project.id, project.id))
        unit.record(factories.event(project.id, project.id))
        assert seen == []
        unit.commit()

    assert seen == [(project.id, 1, True), (project.id, 2, True)]


def test_sequence_continues_after_engine_restart(tmp_path: Path, notifier: EventNotifier) -> None:
    db_path = tmp_path / "numericos.db"
    first = make_engine(db_path)
    migrate.upgrade(first)
    with UnitOfWork(make_session_factory(first), notifier) as unit:
        project = unit.projects.add(factories.project())
        unit.record(factories.event(project.id, project.id))
        unit.record(factories.event(project.id, project.id))
        unit.commit()
    first.dispose()

    second = make_engine(db_path)
    with UnitOfWork(make_session_factory(second), notifier) as unit:
        event = unit.record(factories.event(project.id, project.id))
        unit.commit()
    second.dispose()

    assert event.seq == 3
