"""Lookups and preconditions shared by the use cases."""

from __future__ import annotations

from pathlib import Path

from numericos.core.errors import ExecutionNotTrustedError, NotFoundError, StaleRevisionError
from numericos.persistence.models import (
    AgentMessage,
    AgentSession,
    BoardCard,
    Experiment,
    Hypothesis,
    Project,
    Run,
)
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


def require_hypothesis(uow: UnitOfWork, hypothesis_id: str) -> Hypothesis:
    hypothesis = uow.hypotheses.get(hypothesis_id)
    if hypothesis is None:
        raise NotFoundError(
            f"hypothesis {hypothesis_id} not found",
            details={"resource": "hypothesis", "id": hypothesis_id},
        )
    return hypothesis


def require_experiment(uow: UnitOfWork, experiment_id: str) -> Experiment:
    experiment = uow.experiments.get(experiment_id)
    if experiment is None:
        raise NotFoundError(
            f"experiment {experiment_id} not found",
            details={"resource": "experiment", "id": experiment_id},
        )
    return experiment


def require_run(uow: UnitOfWork, run_id: str) -> Run:
    run = uow.runs.get(run_id)
    if run is None:
        raise NotFoundError(f"run {run_id} not found", details={"resource": "run", "id": run_id})
    return run


def require_agent_session(uow: UnitOfWork, session_id: str) -> AgentSession:
    session = uow.agent_sessions.get(session_id)
    if session is None:
        raise NotFoundError(
            f"agent session {session_id} not found",
            details={"resource": "agent_session", "id": session_id},
        )
    return session


def require_message(uow: UnitOfWork, message_id: str) -> AgentMessage:
    message = uow.messages.get(message_id)
    if message is None:
        raise NotFoundError(
            f"message {message_id} not found", details={"resource": "message", "id": message_id}
        )
    return message


def require_trusted_root(project: Project) -> Path:
    """The directory in which the project's commands may be executed."""
    if project.root_path is None or project.execution_trusted_at is None:
        raise ExecutionNotTrustedError(
            f"project {project.id} is not trusted for execution: running an experiment executes "
            "its code with your permissions, which has to be allowed explicitly for its directory",
            details={"project_id": project.id, "root_path": project.root_path},
        )
    return Path(project.root_path)


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
