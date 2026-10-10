"""Lookups and preconditions shared by the use cases."""

from __future__ import annotations

from numericos.core.errors import NotFoundError, StaleRevisionError
from numericos.persistence.models import BoardCard, Project
from numericos.persistence.unit_of_work import UnitOfWork


def require_project(uow: UnitOfWork, project_id: str) -> Project:
    project = uow.projects.get(project_id)
    if project is None:
        raise NotFoundError(
            f"project {project_id} not found", details={"resource": "project", "id": project_id}
        )
    return project


def require_card(uow: UnitOfWork, card_id: str) -> BoardCard:
    card = uow.cards.get(card_id)
    if card is None:
        raise NotFoundError(
            f"card {card_id} not found", details={"resource": "card", "id": card_id}
        )
    return card


def check_version(resource: str, resource_id: str, *, current: int, provided: int) -> None:
    """Optimistic locking: the caller must have seen the current version."""
    if current != provided:
        raise StaleRevisionError(
            f"{resource} {resource_id} is at version {current}, the request sent {provided}",
            details={
                "resource": resource,
                "id": resource_id,
                "current_version": current,
                "provided_version": provided,
            },
        )
