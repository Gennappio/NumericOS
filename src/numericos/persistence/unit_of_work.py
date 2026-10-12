"""One transaction per mutation: state change and ledger event commit together.

Subscribers are woken only after ``session.commit()`` returned, so publishing without a durable
commit is structurally impossible. Leaving the block without ``commit()`` discards everything.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from numericos.events.notifier import EventNotifier
from numericos.persistence.models import Event
from numericos.persistence.repositories import (
    ArtifactRepository,
    CardRepository,
    EventRepository,
    ExperimentRepository,
    HypothesisRepository,
    ProjectRepository,
    RunRepository,
    WorkerRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], notifier: EventNotifier) -> None:
        self._session_factory = session_factory
        self._notifier = notifier
        self._recorded: list[Event] = []

    def __enter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        self.projects = ProjectRepository(self.session)
        self.cards = CardRepository(self.session)
        self.events = EventRepository(self.session)
        self.hypotheses = HypothesisRepository(self.session)
        self.experiments = ExperimentRepository(self.session)
        self.runs = RunRepository(self.session)
        self.workers = WorkerRepository(self.session)
        self.artifacts = ArtifactRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self.session.rollback()
        finally:
            # close() discards any uncommitted transaction without expiring the objects that
            # were loaded, so read-only blocks can hand them to the caller.
            self.session.close()

    def record(self, event: Event) -> Event:
        """Append a ledger row in this transaction; it is published only after commit."""
        self.events.append(event)
        self._recorded.append(event)
        return event

    def commit(self) -> None:
        self.session.commit()
        published, self._recorded = self._recorded, []
        for event in published:
            self._notifier.publish(event.project_id, event.seq)
