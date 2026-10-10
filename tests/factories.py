"""Builders for ORM objects used across persistence tests."""

from __future__ import annotations

from typing import Any

from numericos.core.enums import CardType, EventType, WorkflowStatus
from numericos.core.ids import new_id
from numericos.events.ledger import EventContext, build_event
from numericos.persistence.engine import utcnow
from numericos.persistence.models import BoardCard, Event, Project


def project(**overrides: Any) -> Project:
    now = utcnow()
    values: dict[str, Any] = {
        "id": new_id("prj"),
        "name": "Heat equation study",
        "research_question": "Does a smaller dt restore stability?",
        "description": "",
        "root_path": None,
        "is_demo": False,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    return Project(**{**values, **overrides})


def card(project_id: str, **overrides: Any) -> BoardCard:
    now = utcnow()
    values: dict[str, Any] = {
        "id": new_id("card"),
        "project_id": project_id,
        "type": CardType.HYPOTHESIS.value,
        "title": "Sparse kernel cache locality",
        "description": "",
        "workflow_status": WorkflowStatus.BACKLOG.value,
        "sort_order": 0,
        "entity_ref": None,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    return BoardCard(**{**values, **overrides})


def context(actor: str = "test:unit") -> EventContext:
    return EventContext(actor=actor, correlation_id=new_id("cor"))


def event(project_id: str, subject_id: str, **overrides: Any) -> Event:
    values: dict[str, Any] = {
        "event_type": EventType.PROJECT_CREATED,
        "project_id": project_id,
        "subject_id": subject_id,
        "payload": {"project": {"id": subject_id}},
        "context": context(),
    }
    return build_event(**{**values, **overrides})
